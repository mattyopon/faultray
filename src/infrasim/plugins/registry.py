"""Plugin registry for custom scenarios and analyzers."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Protocol
import importlib.util
import json
import logging

if TYPE_CHECKING:
    from infrasim.model.graph import InfraGraph

logger = logging.getLogger(__name__)


class ScenarioPlugin(Protocol):
    """Interface for custom scenario plugins."""
    name: str
    description: str
    def generate_scenarios(self, graph, component_ids, components) -> list: ...


class AnalyzerPlugin(Protocol):
    """Interface for custom analyzer plugins."""
    name: str
    def analyze(self, graph, report) -> dict: ...


class EnginePlugin(Protocol):
    """Custom simulation engine plugin."""
    name: str
    description: str
    def simulate(self, graph: InfraGraph, scenarios: list) -> dict: ...


class ReporterPlugin(Protocol):
    """Custom report generation plugin."""
    name: str
    def generate(self, graph: InfraGraph, results: dict) -> str: ...


class DiscoveryPlugin(Protocol):
    """Custom infrastructure discovery plugin."""
    name: str
    def discover(self, config: dict) -> InfraGraph: ...


class PluginRegistry:
    """Central registry for scenario and analyzer plugins.

    Plugins can be registered programmatically or loaded from a directory
    of Python files.  Each file may expose a ``register(registry)`` function
    that will be called automatically during loading.
    """

    _scenario_plugins: list[ScenarioPlugin] = []
    _analyzer_plugins: list[AnalyzerPlugin] = []
    _engine_plugins: list[EnginePlugin] = []
    _reporter_plugins: list[ReporterPlugin] = []
    _discovery_plugins: list[DiscoveryPlugin] = []

    @classmethod
    def register_scenario(cls, plugin: ScenarioPlugin):
        cls._scenario_plugins.append(plugin)

    @classmethod
    def register_analyzer(cls, plugin: AnalyzerPlugin):
        cls._analyzer_plugins.append(plugin)

    @classmethod
    def register_engine(cls, plugin: EnginePlugin):
        cls._engine_plugins.append(plugin)

    @classmethod
    def register_reporter(cls, plugin: ReporterPlugin):
        cls._reporter_plugins.append(plugin)

    @classmethod
    def register_discovery(cls, plugin: DiscoveryPlugin):
        cls._discovery_plugins.append(plugin)

    @classmethod
    def load_plugins_from_dir(cls, plugin_dir: Path):
        """Load all .py files from a directory as plugins."""
        if not plugin_dir.exists():
            return
        for py_file in sorted(plugin_dir.glob("*.py")):
            if py_file.name.startswith("_"):
                continue
            try:
                spec = importlib.util.spec_from_file_location(py_file.stem, py_file)
                if spec and spec.loader:
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)
                    # Auto-register if module has register() function
                    if hasattr(module, "register"):
                        module.register(cls)
                    logger.debug("Loaded plugin: %s", py_file.name)
            except Exception:
                logger.warning("Failed to load plugin %s", py_file, exc_info=True)

    @classmethod
    def get_scenario_plugins(cls) -> list[ScenarioPlugin]:
        return list(cls._scenario_plugins)

    @classmethod
    def get_analyzer_plugins(cls) -> list[AnalyzerPlugin]:
        return list(cls._analyzer_plugins)

    @classmethod
    def get_engines(cls) -> list[EnginePlugin]:
        return list(cls._engine_plugins)

    @classmethod
    def get_reporters(cls) -> list[ReporterPlugin]:
        return list(cls._reporter_plugins)

    @classmethod
    def get_discoveries(cls) -> list[DiscoveryPlugin]:
        return list(cls._discovery_plugins)

    @classmethod
    def clear(cls):
        cls._scenario_plugins.clear()
        cls._analyzer_plugins.clear()
        cls._engine_plugins.clear()
        cls._reporter_plugins.clear()
        cls._discovery_plugins.clear()
