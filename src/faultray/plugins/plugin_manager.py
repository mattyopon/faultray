# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Business Source License 1.1. See LICENSE file for details.

"""Enhanced Plugin System with hot-reloading and marketplace integration.

Plugins can extend FaultZero with:
- Custom scenario generators
- Custom analyzers
- Custom report formats
- Custom discovery providers
- Custom notification channels
- Custom compliance frameworks

Plugin discovery:
1. Built-in plugins (in this package)
2. Installed packages with ``faultzero.plugins`` entry point
3. Local plugins in ``~/.faultzero/plugins/``
4. Plugins loaded from Python files at runtime
"""

from __future__ import annotations

import importlib
import importlib.util
import logging
import sys
import textwrap
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# Default user plugin directory
_DEFAULT_PLUGIN_DIR = Path.home() / ".faultzero" / "plugins"


# ---------------------------------------------------------------------------
# PluginType enum
# ---------------------------------------------------------------------------

class PluginType(str, Enum):
    """Supported plugin categories."""

    SCENARIO_GENERATOR = "scenario_generator"
    ANALYZER = "analyzer"
    REPORTER = "reporter"
    DISCOVERY = "discovery"
    NOTIFICATION = "notification"
    COMPLIANCE = "compliance"
    TRANSFORMER = "transformer"


# ---------------------------------------------------------------------------
# PluginMetadata
# ---------------------------------------------------------------------------

@dataclass
class PluginMetadata:
    """Metadata describing a discovered plugin."""

    name: str
    version: str
    author: str
    description: str
    plugin_type: PluginType
    entry_point: str  # Python dotted path or file path
    dependencies: list[str] = field(default_factory=list)
    config_schema: dict | None = None
    enabled: bool = True
    source: str = ""  # "builtin", "entrypoint", "local", "runtime"

    def to_dict(self) -> dict[str, Any]:
        """Serialise metadata to a dictionary."""
        return {
            "name": self.name,
            "version": self.version,
            "author": self.author,
            "description": self.description,
            "plugin_type": self.plugin_type.value,
            "entry_point": self.entry_point,
            "dependencies": self.dependencies,
            "config_schema": self.config_schema,
            "enabled": self.enabled,
            "source": self.source,
        }


# ---------------------------------------------------------------------------
# PluginContext (passed to plugins at execution time)
# ---------------------------------------------------------------------------

@dataclass
class PluginContext:
    """Execution context supplied to a plugin when it runs."""

    graph: Any = None  # InfraGraph | None
    sim_report: Any = None  # SimulationReport | None
    config: dict = field(default_factory=dict)
    output_dir: Path | None = None


# ---------------------------------------------------------------------------
# PluginInterface protocol
# ---------------------------------------------------------------------------

@runtime_checkable
class PluginInterface(Protocol):
    """Protocol that all plugins must satisfy."""

    name: str
    version: str
    plugin_type: str  # value of PluginType enum

    def initialize(self, config: dict) -> None:
        """Perform one-time setup with user-supplied configuration."""
        ...

    def execute(self, context: PluginContext) -> Any:
        """Run the plugin logic and return results."""
        ...


# ---------------------------------------------------------------------------
# PluginManager
# ---------------------------------------------------------------------------

class PluginManager:
    """Discover, load, manage, and execute FaultZero plugins.

    The manager maintains an internal registry of loaded plugins and their
    metadata.  Plugins can be discovered automatically from several sources
    or loaded manually at runtime.
    """

    def __init__(self, plugin_dirs: list[Path] | None = None) -> None:
        self._plugins: dict[str, PluginInterface] = {}
        self._metadata: dict[str, PluginMetadata] = {}
        self._plugin_modules: dict[str, Any] = {}  # for hot-reload
        self._plugin_dirs = plugin_dirs or [_DEFAULT_PLUGIN_DIR]
        self._disabled: set[str] = set()

    # ---- Discovery --------------------------------------------------------

    def discover(self) -> list[PluginMetadata]:
        """Discover all available plugins from all configured sources.

        Returns:
            List of ``PluginMetadata`` for every discovered plugin.
        """
        discovered: list[PluginMetadata] = []
        discovered.extend(self._discover_local_plugins())
        discovered.extend(self._discover_entrypoint_plugins())
        return discovered

    def _discover_local_plugins(self) -> list[PluginMetadata]:
        """Scan configured plugin directories for Python files with PLUGIN_METADATA."""
        found: list[PluginMetadata] = []
        for plugin_dir in self._plugin_dirs:
            if not plugin_dir.exists():
                continue
            for py_file in sorted(plugin_dir.glob("*.py")):
                if py_file.name.startswith("_"):
                    continue
                meta = self._read_metadata_from_file(py_file)
                if meta is not None:
                    found.append(meta)
        return found

    def _discover_entrypoint_plugins(self) -> list[PluginMetadata]:
        """Find installed packages declaring the ``faultzero.plugins`` entry-point group."""
        found: list[PluginMetadata] = []
        try:
            if sys.version_info >= (3, 12):
                from importlib.metadata import entry_points

                eps = entry_points(group="faultzero.plugins")
            else:
                from importlib.metadata import entry_points

                all_eps = entry_points()
                eps = all_eps.get("faultzero.plugins", [])

            for ep in eps:
                try:
                    plugin_type_str = getattr(ep, "extras", ["scenario_generator"])
                    ptype = PluginType(plugin_type_str[0] if plugin_type_str else "scenario_generator")
                except (ValueError, IndexError):
                    ptype = PluginType.SCENARIO_GENERATOR

                meta = PluginMetadata(
                    name=ep.name,
                    version="0.0.0",
                    author="unknown",
                    description=f"Installed plugin: {ep.name}",
                    plugin_type=ptype,
                    entry_point=ep.value,
                    source="entrypoint",
                )
                found.append(meta)
        except Exception:
            logger.debug("Entry point discovery failed", exc_info=True)
        return found

    @staticmethod
    def _read_metadata_from_file(py_file: Path) -> PluginMetadata | None:
        """Extract ``PLUGIN_METADATA`` dict from a Python source file."""
        try:
            spec = importlib.util.spec_from_file_location(py_file.stem, py_file)
            if spec is None or spec.loader is None:
                return None
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)  # type: ignore[union-attr]

            raw = getattr(module, "PLUGIN_METADATA", None)
            if not isinstance(raw, dict):
                return None

            try:
                ptype = PluginType(raw.get("type", "scenario_generator"))
            except ValueError:
                ptype = PluginType.SCENARIO_GENERATOR

            return PluginMetadata(
                name=raw.get("name", py_file.stem),
                version=raw.get("version", "0.0.0"),
                author=raw.get("author", "unknown"),
                description=raw.get("description", ""),
                plugin_type=ptype,
                entry_point=str(py_file),
                dependencies=raw.get("dependencies", []),
                config_schema=raw.get("config_schema"),
                enabled=raw.get("enabled", True),
                source="local",
            )
        except Exception:
            logger.debug("Failed to read metadata from %s", py_file, exc_info=True)
            return None

    # ---- Loading -----------------------------------------------------------

    def load(self, plugin_name: str) -> PluginInterface:
        """Load a plugin by name (must have been discovered first or manually registered).

        Args:
            plugin_name: Name of the plugin to load.

        Returns:
            The loaded ``PluginInterface`` instance.

        Raises:
            KeyError: If the plugin has not been discovered or registered.
            RuntimeError: If loading fails.
        """
        # Already loaded
        if plugin_name in self._plugins:
            return self._plugins[plugin_name]

        meta = self._metadata.get(plugin_name)
        if meta is None:
            # Attempt auto-discovery first
            for m in self.discover():
                if m.name not in self._metadata:
                    self._metadata[m.name] = m
            meta = self._metadata.get(plugin_name)
            if meta is None:
                raise KeyError(f"Plugin '{plugin_name}' not found.")

        plugin = self._instantiate_plugin(meta)
        self._plugins[plugin_name] = plugin
        return plugin

    def load_all(self) -> dict[str, PluginInterface]:
        """Discover and load all available plugins.

        Returns:
            Dictionary mapping plugin name to loaded ``PluginInterface``.
        """
        for meta in self.discover():
            if meta.name not in self._metadata:
                self._metadata[meta.name] = meta
        for name, meta in self._metadata.items():
            if name not in self._plugins and meta.enabled and name not in self._disabled:
                try:
                    self._plugins[name] = self._instantiate_plugin(meta)
                except Exception:
                    logger.warning("Failed to load plugin %s", name, exc_info=True)
        return dict(self._plugins)

    def load_from_file(self, file_path: Path | str) -> PluginInterface:
        """Load a plugin from a specific Python file at runtime.

        Args:
            file_path: Path to the ``.py`` file containing the plugin.

        Returns:
            The loaded ``PluginInterface`` instance.
        """
        file_path = Path(file_path)
        meta = self._read_metadata_from_file(file_path)
        if meta is None:
            raise RuntimeError(f"Could not read PLUGIN_METADATA from {file_path}")
        meta.source = "runtime"
        self._metadata[meta.name] = meta
        plugin = self._instantiate_plugin(meta)
        self._plugins[meta.name] = plugin
        return plugin

    def _instantiate_plugin(self, meta: PluginMetadata) -> PluginInterface:
        """Create a plugin instance from metadata."""
        entry = meta.entry_point

        # File-based plugin (local / runtime)
        if entry.endswith(".py") or Path(entry).is_file():
            return self._load_from_file_path(Path(entry), meta.name)

        # Dotted-path entry point (installed package)
        module_path, _, attr_name = entry.rpartition(":")
        if not module_path:
            module_path, _, attr_name = entry.rpartition(".")
        if not module_path:
            raise RuntimeError(f"Invalid entry_point: {entry}")

        mod = importlib.import_module(module_path)
        cls_or_factory = getattr(mod, attr_name, None)
        if cls_or_factory is None:
            raise RuntimeError(
                f"Entry point '{entry}' resolved module '{module_path}' "
                f"but attribute '{attr_name}' was not found."
            )

        plugin = cls_or_factory() if callable(cls_or_factory) else cls_or_factory
        return plugin  # type: ignore[return-value]

    def _load_from_file_path(self, py_file: Path, plugin_name: str) -> PluginInterface:
        """Import a Python file and find the plugin class inside.

        Uses ``compile`` + ``exec`` rather than ``importlib`` to avoid
        bytecode caching, which is essential for hot-reload support.
        """
        import types

        source = py_file.read_text(encoding="utf-8")
        code = compile(source, str(py_file), "exec")

        module = types.ModuleType(f"_fz_plugin_{py_file.stem}")
        module.__file__ = str(py_file)
        exec(code, module.__dict__)  # noqa: S102
        self._plugin_modules[plugin_name] = module

        # Look for a class that matches PluginInterface (has name, version, execute)
        for attr_name in dir(module):
            obj = getattr(module, attr_name)
            if (
                isinstance(obj, type)
                and hasattr(obj, "name")
                and hasattr(obj, "execute")
                and attr_name != "PluginInterface"
            ):
                instance = obj()
                return instance  # type: ignore[return-value]

        raise RuntimeError(
            f"No plugin class found in {py_file}. "
            "The file must contain a class with 'name', 'version', 'plugin_type', "
            "'initialize', and 'execute' attributes."
        )

    # ---- Registration -----------------------------------------------------

    def register(self, plugin: PluginInterface) -> None:
        """Manually register a plugin instance.

        Args:
            plugin: An object implementing the ``PluginInterface`` protocol.
        """
        name = plugin.name
        self._plugins[name] = plugin

        # Build metadata from the plugin object
        try:
            ptype = PluginType(plugin.plugin_type)
        except ValueError:
            ptype = PluginType.SCENARIO_GENERATOR

        self._metadata[name] = PluginMetadata(
            name=name,
            version=getattr(plugin, "version", "0.0.0"),
            author=getattr(plugin, "author", "unknown"),
            description=getattr(plugin, "description", ""),
            plugin_type=ptype,
            entry_point="<registered>",
            source="runtime",
        )

    def unregister(self, plugin_name: str) -> None:
        """Remove a plugin from the registry.

        Args:
            plugin_name: Name of the plugin to remove.
        """
        self._plugins.pop(plugin_name, None)
        self._metadata.pop(plugin_name, None)
        self._plugin_modules.pop(plugin_name, None)

    # ---- Execution ---------------------------------------------------------

    def execute(self, plugin_name: str, context: PluginContext) -> Any:
        """Execute a plugin by name.

        Args:
            plugin_name: Name of the plugin.
            context: Execution context.

        Returns:
            Whatever the plugin's ``execute`` method returns.

        Raises:
            KeyError: If the plugin is not loaded.
            RuntimeError: If the plugin is disabled.
        """
        if plugin_name in self._disabled:
            raise RuntimeError(f"Plugin '{plugin_name}' is disabled.")

        plugin = self._plugins.get(plugin_name)
        if plugin is None:
            plugin = self.load(plugin_name)

        return plugin.execute(context)

    # ---- Listing / querying -----------------------------------------------

    def list_plugins(self) -> list[PluginMetadata]:
        """Return metadata for all known (discovered + registered) plugins.

        Returns:
            List of ``PluginMetadata``.
        """
        # Merge discovered with already-known
        for meta in self.discover():
            if meta.name not in self._metadata:
                self._metadata[meta.name] = meta
        metas = list(self._metadata.values())
        # Apply disabled state
        for m in metas:
            if m.name in self._disabled:
                m.enabled = False
        return metas

    def get_plugins_by_type(self, ptype: PluginType) -> list[PluginMetadata]:
        """Return metadata for plugins matching a specific type.

        Args:
            ptype: Plugin type to filter by.

        Returns:
            List of matching ``PluginMetadata``.
        """
        return [m for m in self.list_plugins() if m.plugin_type == ptype]

    # ---- Enable / Disable -------------------------------------------------

    def enable(self, plugin_name: str) -> None:
        """Enable a previously disabled plugin.

        Args:
            plugin_name: Name of the plugin.
        """
        self._disabled.discard(plugin_name)
        meta = self._metadata.get(plugin_name)
        if meta:
            meta.enabled = True

    def disable(self, plugin_name: str) -> None:
        """Disable a plugin so it will not be executed.

        Args:
            plugin_name: Name of the plugin.
        """
        self._disabled.add(plugin_name)
        meta = self._metadata.get(plugin_name)
        if meta:
            meta.enabled = False

    # ---- Hot-reload -------------------------------------------------------

    def reload(self, plugin_name: str) -> None:
        """Hot-reload a plugin from its source file.

        This re-reads the plugin file, re-imports the module, and replaces
        the cached plugin instance.

        Args:
            plugin_name: Name of the plugin to reload.

        Raises:
            KeyError: If the plugin is not known.
            RuntimeError: If the plugin cannot be reloaded (e.g. not file-based).
        """
        meta = self._metadata.get(plugin_name)
        if meta is None:
            raise KeyError(f"Plugin '{plugin_name}' not found.")

        entry = meta.entry_point
        if not entry.endswith(".py") and not Path(entry).is_file():
            raise RuntimeError(
                f"Plugin '{plugin_name}' was loaded from an entry-point or "
                "registered at runtime; hot-reload requires a file-based plugin."
            )

        # Remove old module from sys.modules
        old_module = self._plugin_modules.pop(plugin_name, None)
        if old_module is not None:
            mod_name = getattr(old_module, "__name__", None)
            if mod_name and mod_name in sys.modules:
                del sys.modules[mod_name]

        # Re-load
        self._plugins.pop(plugin_name, None)
        plugin = self._load_from_file_path(Path(entry), plugin_name)
        self._plugins[plugin_name] = plugin
        logger.info("Hot-reloaded plugin: %s", plugin_name)

    # ---- Scaffolding -------------------------------------------------------

    def create_plugin_template(
        self,
        name: str,
        ptype: PluginType,
        output_dir: Path | None = None,
    ) -> Path:
        """Generate a ready-to-use plugin template file.

        Args:
            name: Plugin name (will be used as the file name).
            ptype: Type of plugin to scaffold.
            output_dir: Directory to write the template into.
                Defaults to ``~/.faultzero/plugins/``.

        Returns:
            Path to the created template file.
        """
        output_dir = output_dir or _DEFAULT_PLUGIN_DIR
        output_dir.mkdir(parents=True, exist_ok=True)

        safe_name = name.replace("-", "_").replace(" ", "_")
        class_name = "".join(
            part.capitalize() for part in name.replace("-", "_").split("_")
        ) + "Plugin"

        execute_body = _EXECUTE_BODIES.get(ptype, _DEFAULT_EXECUTE_BODY)

        lines = [
            f'"""FaultZero plugin: {name}.',
            "",
            f"Auto-generated plugin template for type '{ptype.value}'.",
            '"""',
            "",
            "PLUGIN_METADATA = {",
            f'    "name": "{name}",',
            '    "version": "1.0.0",',
            '    "author": "Your Name",',
            f'    "description": "Description of {name}",',
            f'    "type": "{ptype.value}",',
            "}",
            "",
            "",
            f"class {class_name}:",
            f'    """Plugin implementation for {name}."""',
            "",
            f'    name = "{name}"',
            '    version = "1.0.0"',
            f'    plugin_type = "{ptype.value}"',
            "",
            "    def initialize(self, config):",
            '        """One-time setup with user-supplied configuration."""',
            "        self.config = config",
            "",
            "    def execute(self, context):",
            '        """Run the plugin logic."""',
        ]
        # Append execute body lines (already indented with 8 spaces)
        lines.append(execute_body)
        lines.append("")  # trailing newline

        template = "\n".join(lines)

        file_path = output_dir / f"{safe_name}.py"
        file_path.write_text(template)
        logger.info("Created plugin template: %s", file_path)
        return file_path


# ---------------------------------------------------------------------------
# Scaffold execute-body snippets per plugin type
# ---------------------------------------------------------------------------

_INDENT = "        "

_DEFAULT_EXECUTE_BODY = f"""{_INDENT}return {{"status": "ok"}}"""

_EXECUTE_BODIES: dict[PluginType, str] = {
    PluginType.SCENARIO_GENERATOR: textwrap.indent(
        textwrap.dedent("""\
            scenarios = []
            if context.graph is not None:
                for comp in context.graph.components.values():
                    scenarios.append({
                        "name": f"Custom: {comp.name} failure",
                        "fault_type": "component_down",
                        "target": comp.id,
                        "severity": "medium",
                    })
            return scenarios"""),
        _INDENT,
    ),
    PluginType.ANALYZER: textwrap.indent(
        textwrap.dedent("""\
            findings = []
            if context.graph is not None:
                for comp in context.graph.components.values():
                    if comp.replicas <= 1:
                        findings.append({
                            "component": comp.id,
                            "issue": "single replica",
                            "severity": "high",
                        })
            return {"findings": findings}"""),
        _INDENT,
    ),
    PluginType.REPORTER: textwrap.indent(
        textwrap.dedent("""\
            lines = ["# Custom Report"]
            if context.sim_report is not None:
                lines.append(f"Resilience: {context.sim_report.resilience_score}")
            return "\\n".join(lines)"""),
        _INDENT,
    ),
    PluginType.DISCOVERY: textwrap.indent(
        textwrap.dedent("""\
            # Discover infrastructure from an external source
            # Return an InfraGraph or dict
            return {"components": [], "dependencies": []}"""),
        _INDENT,
    ),
    PluginType.NOTIFICATION: textwrap.indent(
        textwrap.dedent("""\
            # Send notification (e.g. Slack, email, PagerDuty)
            message = context.config.get("message", "FaultZero alert")
            print(f"[NOTIFICATION] {message}")
            return {"sent": True}"""),
        _INDENT,
    ),
    PluginType.COMPLIANCE: textwrap.indent(
        textwrap.dedent("""\
            # Check compliance rules against the infrastructure
            rules_passed = 0
            rules_failed = 0
            return {"passed": rules_passed, "failed": rules_failed}"""),
        _INDENT,
    ),
    PluginType.TRANSFORMER: textwrap.indent(
        textwrap.dedent("""\
            # Transform graph or results into another format
            if context.graph is not None:
                return context.graph.to_dict()
            return {}"""),
        _INDENT,
    ),
}
