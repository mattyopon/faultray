"""Tests for the plugin registry and plugin-engine integration."""
from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from infrasim.plugins.registry import PluginRegistry
from infrasim.simulator.scenarios import Fault, FaultType, Scenario


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _clean_registry():
    """Ensure the registry is clean before and after each test."""
    PluginRegistry.clear()
    yield
    PluginRegistry.clear()


class _DummyScenarioPlugin:
    """A minimal scenario plugin for testing."""

    name = "dummy-scenario"
    description = "Generates a single dummy scenario."

    def generate_scenarios(self, graph, component_ids, components) -> list:
        if not component_ids:
            return []
        return [
            Scenario(
                id="plugin-dummy-1",
                name="Plugin Dummy",
                description="Injected by plugin",
                faults=[
                    Fault(
                        target_component_id=component_ids[0],
                        fault_type=FaultType.COMPONENT_DOWN,
                    )
                ],
            )
        ]


class _DummyAnalyzerPlugin:
    """A minimal analyzer plugin for testing."""

    name = "dummy-analyzer"

    def analyze(self, graph, report) -> dict:
        return {"plugin": self.name, "ok": True}


# ---------------------------------------------------------------------------
# Registry tests
# ---------------------------------------------------------------------------

class TestPluginRegistry:
    def test_register_scenario_plugin(self):
        plugin = _DummyScenarioPlugin()
        PluginRegistry.register_scenario(plugin)
        assert len(PluginRegistry.get_scenario_plugins()) == 1
        assert PluginRegistry.get_scenario_plugins()[0].name == "dummy-scenario"

    def test_register_analyzer_plugin(self):
        plugin = _DummyAnalyzerPlugin()
        PluginRegistry.register_analyzer(plugin)
        assert len(PluginRegistry.get_analyzer_plugins()) == 1
        assert PluginRegistry.get_analyzer_plugins()[0].name == "dummy-analyzer"

    def test_clear(self):
        PluginRegistry.register_scenario(_DummyScenarioPlugin())
        PluginRegistry.register_analyzer(_DummyAnalyzerPlugin())
        assert len(PluginRegistry.get_scenario_plugins()) == 1
        assert len(PluginRegistry.get_analyzer_plugins()) == 1

        PluginRegistry.clear()
        assert PluginRegistry.get_scenario_plugins() == []
        assert PluginRegistry.get_analyzer_plugins() == []

    def test_load_plugins_from_dir(self, tmp_path: Path):
        """Write a plugin .py file to a temp dir and load it."""
        plugin_file = tmp_path / "my_plugin.py"
        plugin_file.write_text(
            textwrap.dedent("""\
                from infrasim.simulator.scenarios import Fault, FaultType, Scenario

                class MyPlugin:
                    name = "my-plugin"
                    description = "test plugin"
                    def generate_scenarios(self, graph, component_ids, components):
                        return []

                def register(registry):
                    registry.register_scenario(MyPlugin())
            """)
        )

        PluginRegistry.load_plugins_from_dir(tmp_path)
        assert len(PluginRegistry.get_scenario_plugins()) == 1
        assert PluginRegistry.get_scenario_plugins()[0].name == "my-plugin"

    def test_load_plugins_skips_underscore_files(self, tmp_path: Path):
        """Files starting with _ should be skipped."""
        (tmp_path / "_internal.py").write_text("raise RuntimeError('should not load')")
        PluginRegistry.load_plugins_from_dir(tmp_path)
        assert PluginRegistry.get_scenario_plugins() == []

    def test_load_plugins_nonexistent_dir(self, tmp_path: Path):
        """Loading from a non-existent directory should be a no-op."""
        PluginRegistry.load_plugins_from_dir(tmp_path / "nonexistent")
        assert PluginRegistry.get_scenario_plugins() == []


# ---------------------------------------------------------------------------
# Engine integration
# ---------------------------------------------------------------------------

class TestPluginEngineIntegration:
    def test_plugin_scenarios_merged_into_simulation(self):
        """Plugin-generated scenarios should appear in simulation results."""
        from infrasim.model.demo import create_demo_graph
        from infrasim.simulator.engine import SimulationEngine

        graph = create_demo_graph()
        plugin = _DummyScenarioPlugin()
        PluginRegistry.register_scenario(plugin)

        engine = SimulationEngine(graph)
        report = engine.run_all_defaults(include_feed=False, include_plugins=True)

        # The plugin adds one scenario with id "plugin-dummy-1"
        plugin_ids = [r.scenario.id for r in report.results if r.scenario.id == "plugin-dummy-1"]
        assert len(plugin_ids) == 1

    def test_simulation_without_plugins(self):
        """Simulation should work with no plugins registered."""
        from infrasim.model.demo import create_demo_graph
        from infrasim.simulator.engine import SimulationEngine

        graph = create_demo_graph()
        engine = SimulationEngine(graph)
        report = engine.run_all_defaults(include_feed=False, include_plugins=True)

        # Should still have default scenarios
        assert len(report.results) > 0


# ---------------------------------------------------------------------------
# Additional plugin type tests: Engine, Reporter, Discovery
# ---------------------------------------------------------------------------


class _DummyEnginePlugin:
    """A minimal engine plugin for testing."""

    name = "dummy-engine"
    description = "A dummy simulation engine."

    def simulate(self, graph, scenarios):
        return {"engine": self.name, "scenario_count": len(scenarios)}


class _DummyReporterPlugin:
    """A minimal reporter plugin for testing."""

    name = "dummy-reporter"

    def generate(self, graph, results):
        return f"Report from {self.name}"


class _DummyDiscoveryPlugin:
    """A minimal discovery plugin for testing."""

    name = "dummy-discovery"

    def discover(self, config):
        from infrasim.model.graph import InfraGraph
        return InfraGraph()


class TestEnginePlugin:
    """Tests for EnginePlugin registration and retrieval."""

    def test_register_engine_plugin(self):
        plugin = _DummyEnginePlugin()
        PluginRegistry.register_engine(plugin)
        engines = PluginRegistry.get_engines()
        assert len(engines) == 1
        assert engines[0].name == "dummy-engine"

    def test_engine_plugin_simulate(self):
        plugin = _DummyEnginePlugin()
        result = plugin.simulate(None, [1, 2, 3])
        assert result["engine"] == "dummy-engine"
        assert result["scenario_count"] == 3

    def test_clear_removes_engine_plugins(self):
        PluginRegistry.register_engine(_DummyEnginePlugin())
        assert len(PluginRegistry.get_engines()) == 1
        PluginRegistry.clear()
        assert len(PluginRegistry.get_engines()) == 0


class TestReporterPlugin:
    """Tests for ReporterPlugin registration and retrieval."""

    def test_register_reporter_plugin(self):
        plugin = _DummyReporterPlugin()
        PluginRegistry.register_reporter(plugin)
        reporters = PluginRegistry.get_reporters()
        assert len(reporters) == 1
        assert reporters[0].name == "dummy-reporter"

    def test_reporter_plugin_generate(self):
        plugin = _DummyReporterPlugin()
        result = plugin.generate(None, {})
        assert "dummy-reporter" in result

    def test_clear_removes_reporter_plugins(self):
        PluginRegistry.register_reporter(_DummyReporterPlugin())
        assert len(PluginRegistry.get_reporters()) == 1
        PluginRegistry.clear()
        assert len(PluginRegistry.get_reporters()) == 0


class TestDiscoveryPlugin:
    """Tests for DiscoveryPlugin registration and retrieval."""

    def test_register_discovery_plugin(self):
        plugin = _DummyDiscoveryPlugin()
        PluginRegistry.register_discovery(plugin)
        discoveries = PluginRegistry.get_discoveries()
        assert len(discoveries) == 1
        assert discoveries[0].name == "dummy-discovery"

    def test_discovery_plugin_discover(self):
        from infrasim.model.graph import InfraGraph
        plugin = _DummyDiscoveryPlugin()
        graph = plugin.discover({})
        assert isinstance(graph, InfraGraph)

    def test_clear_removes_discovery_plugins(self):
        PluginRegistry.register_discovery(_DummyDiscoveryPlugin())
        assert len(PluginRegistry.get_discoveries()) == 1
        PluginRegistry.clear()
        assert len(PluginRegistry.get_discoveries()) == 0


class TestMultiplePluginTypes:
    """Test registering multiple plugin types simultaneously."""

    def test_register_all_types(self):
        PluginRegistry.register_scenario(_DummyScenarioPlugin())
        PluginRegistry.register_analyzer(_DummyAnalyzerPlugin())
        PluginRegistry.register_engine(_DummyEnginePlugin())
        PluginRegistry.register_reporter(_DummyReporterPlugin())
        PluginRegistry.register_discovery(_DummyDiscoveryPlugin())

        assert len(PluginRegistry.get_scenario_plugins()) == 1
        assert len(PluginRegistry.get_analyzer_plugins()) == 1
        assert len(PluginRegistry.get_engines()) == 1
        assert len(PluginRegistry.get_reporters()) == 1
        assert len(PluginRegistry.get_discoveries()) == 1

    def test_clear_removes_all_types(self):
        PluginRegistry.register_scenario(_DummyScenarioPlugin())
        PluginRegistry.register_analyzer(_DummyAnalyzerPlugin())
        PluginRegistry.register_engine(_DummyEnginePlugin())
        PluginRegistry.register_reporter(_DummyReporterPlugin())
        PluginRegistry.register_discovery(_DummyDiscoveryPlugin())

        PluginRegistry.clear()

        assert len(PluginRegistry.get_scenario_plugins()) == 0
        assert len(PluginRegistry.get_analyzer_plugins()) == 0
        assert len(PluginRegistry.get_engines()) == 0
        assert len(PluginRegistry.get_reporters()) == 0
        assert len(PluginRegistry.get_discoveries()) == 0

    def test_multiple_plugins_same_type(self):
        PluginRegistry.register_scenario(_DummyScenarioPlugin())
        PluginRegistry.register_scenario(_DummyScenarioPlugin())
        assert len(PluginRegistry.get_scenario_plugins()) == 2


class TestLoadPluginsFromDirExtended:
    """Extended tests for plugin loading from directory."""

    def test_load_plugin_with_bad_code(self, tmp_path: Path):
        """Plugin files with syntax errors should be skipped gracefully."""
        bad_file = tmp_path / "bad_plugin.py"
        bad_file.write_text("def register(registry):\n    raise RuntimeError('boom')\n")
        PluginRegistry.load_plugins_from_dir(tmp_path)
        # Should not crash, and no plugins should be registered
        assert len(PluginRegistry.get_scenario_plugins()) == 0

    def test_load_plugin_without_register_function(self, tmp_path: Path):
        """Plugin files without register() should be loaded but not register anything."""
        plugin_file = tmp_path / "no_register.py"
        plugin_file.write_text("x = 42\n")
        PluginRegistry.load_plugins_from_dir(tmp_path)
        assert len(PluginRegistry.get_scenario_plugins()) == 0

    def test_load_multiple_plugins(self, tmp_path: Path):
        """Multiple plugin files should all be loaded."""
        for i in range(3):
            plugin_file = tmp_path / f"plugin_{i}.py"
            plugin_file.write_text(textwrap.dedent(f"""\
                class Plugin{i}:
                    name = "plugin-{i}"
                    description = "Plugin {i}"
                    def generate_scenarios(self, graph, component_ids, components):
                        return []

                def register(registry):
                    registry.register_scenario(Plugin{i}())
            """))
        PluginRegistry.load_plugins_from_dir(tmp_path)
        assert len(PluginRegistry.get_scenario_plugins()) == 3
