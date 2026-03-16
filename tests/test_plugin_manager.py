"""Tests for the enhanced plugin manager system."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from faultray.plugins.plugin_manager import (
    PluginContext,
    PluginManager,
    PluginMetadata,
    PluginType,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_sample_plugin(tmp_path: Path, name: str = "test-plugin") -> Path:
    """Write a minimal valid plugin file and return its path."""
    safe_name = name.replace("-", "_")
    class_name = "".join(
        part.capitalize() for part in name.replace("-", "_").split("_")
    ) + "Plugin"

    code = textwrap.dedent(f'''\
        PLUGIN_METADATA = {{
            "name": "{name}",
            "version": "1.0.0",
            "author": "Test Author",
            "description": "A test plugin",
            "type": "scenario_generator",
        }}

        class {class_name}:
            name = "{name}"
            version = "1.0.0"
            plugin_type = "scenario_generator"

            def initialize(self, config):
                self.config = config

            def execute(self, context):
                scenarios = []
                if context.graph is not None:
                    for comp in context.graph.components.values():
                        scenarios.append({{
                            "name": f"Test: {{comp.name}} failure",
                            "target": comp.id,
                        }})
                return scenarios
    ''')
    plugin_file = tmp_path / f"{safe_name}.py"
    plugin_file.write_text(code)
    return plugin_file


def _write_analyzer_plugin(tmp_path: Path, name: str = "test-analyzer") -> Path:
    """Write a minimal analyzer plugin file."""
    safe_name = name.replace("-", "_")
    code = textwrap.dedent(f'''\
        PLUGIN_METADATA = {{
            "name": "{name}",
            "version": "2.0.0",
            "author": "Test Author",
            "description": "An analyzer plugin",
            "type": "analyzer",
        }}

        class TestAnalyzerPlugin:
            name = "{name}"
            version = "2.0.0"
            plugin_type = "analyzer"

            def initialize(self, config):
                self.config = config

            def execute(self, context):
                return {{"analyzed": True, "components": len(context.graph.components) if context.graph else 0}}
    ''')
    plugin_file = tmp_path / f"{safe_name}.py"
    plugin_file.write_text(code)
    return plugin_file


# ---------------------------------------------------------------------------
# PluginType tests
# ---------------------------------------------------------------------------

class TestPluginType:
    def test_all_types_exist(self):
        expected = [
            "scenario_generator", "analyzer", "reporter", "discovery",
            "notification", "compliance", "transformer",
        ]
        for t in expected:
            assert PluginType(t) is not None

    def test_invalid_type_raises(self):
        with pytest.raises(ValueError):
            PluginType("nonexistent")


# ---------------------------------------------------------------------------
# PluginMetadata tests
# ---------------------------------------------------------------------------

class TestPluginMetadata:
    def test_to_dict(self):
        meta = PluginMetadata(
            name="test",
            version="1.0.0",
            author="Author",
            description="Test plugin",
            plugin_type=PluginType.ANALYZER,
            entry_point="test.py",
        )
        d = meta.to_dict()
        assert d["name"] == "test"
        assert d["version"] == "1.0.0"
        assert d["plugin_type"] == "analyzer"
        assert d["enabled"] is True

    def test_defaults(self):
        meta = PluginMetadata(
            name="test",
            version="0.0.0",
            author="",
            description="",
            plugin_type=PluginType.SCENARIO_GENERATOR,
            entry_point="",
        )
        assert meta.enabled is True
        assert meta.dependencies == []
        assert meta.config_schema is None
        assert meta.source == ""


# ---------------------------------------------------------------------------
# PluginContext tests
# ---------------------------------------------------------------------------

class TestPluginContext:
    def test_default_context(self):
        ctx = PluginContext()
        assert ctx.graph is None
        assert ctx.sim_report is None
        assert ctx.config == {}
        assert ctx.output_dir is None

    def test_context_with_values(self):
        ctx = PluginContext(config={"key": "value"}, output_dir=Path("/tmp"))
        assert ctx.config["key"] == "value"
        assert ctx.output_dir == Path("/tmp")


# ---------------------------------------------------------------------------
# PluginManager - Discovery tests
# ---------------------------------------------------------------------------

class TestPluginManagerDiscovery:
    def test_discover_empty_dir(self, tmp_path: Path):
        manager = PluginManager(plugin_dirs=[tmp_path])
        metas = manager.discover()
        assert metas == []

    def test_discover_nonexistent_dir(self):
        manager = PluginManager(plugin_dirs=[Path("/nonexistent/path")])
        metas = manager.discover()
        assert metas == []

    def test_discover_local_plugin(self, tmp_path: Path):
        _write_sample_plugin(tmp_path, "my-scenario")
        manager = PluginManager(plugin_dirs=[tmp_path])
        metas = manager.discover()
        assert len(metas) == 1
        assert metas[0].name == "my-scenario"
        assert metas[0].version == "1.0.0"
        assert metas[0].plugin_type == PluginType.SCENARIO_GENERATOR
        assert metas[0].source == "local"

    def test_discover_multiple_plugins(self, tmp_path: Path):
        _write_sample_plugin(tmp_path, "plugin-a")
        _write_analyzer_plugin(tmp_path, "plugin-b")
        manager = PluginManager(plugin_dirs=[tmp_path])
        metas = manager.discover()
        assert len(metas) == 2
        names = {m.name for m in metas}
        assert names == {"plugin-a", "plugin-b"}

    def test_discover_skips_underscore_files(self, tmp_path: Path):
        (tmp_path / "_internal.py").write_text("PLUGIN_METADATA = {'name': 'x'}")
        manager = PluginManager(plugin_dirs=[tmp_path])
        metas = manager.discover()
        assert len(metas) == 0

    def test_discover_skips_invalid_files(self, tmp_path: Path):
        (tmp_path / "broken.py").write_text("raise RuntimeError('broken')")
        manager = PluginManager(plugin_dirs=[tmp_path])
        # Should not raise, just return empty
        metas = manager.discover()
        assert len(metas) == 0

    def test_discover_skips_files_without_metadata(self, tmp_path: Path):
        (tmp_path / "no_meta.py").write_text("x = 42")
        manager = PluginManager(plugin_dirs=[tmp_path])
        metas = manager.discover()
        assert len(metas) == 0


# ---------------------------------------------------------------------------
# PluginManager - Loading tests
# ---------------------------------------------------------------------------

class TestPluginManagerLoading:
    def test_load_from_file(self, tmp_path: Path):
        plugin_file = _write_sample_plugin(tmp_path, "file-plugin")
        manager = PluginManager(plugin_dirs=[tmp_path])
        plugin = manager.load_from_file(plugin_file)
        assert plugin.name == "file-plugin"
        assert plugin.version == "1.0.0"

    def test_load_by_name_after_discover(self, tmp_path: Path):
        _write_sample_plugin(tmp_path, "named-plugin")
        manager = PluginManager(plugin_dirs=[tmp_path])
        plugin = manager.load("named-plugin")
        assert plugin.name == "named-plugin"

    def test_load_caches_plugin(self, tmp_path: Path):
        _write_sample_plugin(tmp_path, "cached-plugin")
        manager = PluginManager(plugin_dirs=[tmp_path])
        p1 = manager.load("cached-plugin")
        p2 = manager.load("cached-plugin")
        assert p1 is p2

    def test_load_unknown_raises(self, tmp_path: Path):
        manager = PluginManager(plugin_dirs=[tmp_path])
        with pytest.raises(KeyError, match="not found"):
            manager.load("nonexistent-plugin")

    def test_load_all(self, tmp_path: Path):
        _write_sample_plugin(tmp_path, "all-a")
        _write_analyzer_plugin(tmp_path, "all-b")
        manager = PluginManager(plugin_dirs=[tmp_path])
        plugins = manager.load_all()
        assert len(plugins) == 2
        assert "all-a" in plugins
        assert "all-b" in plugins


# ---------------------------------------------------------------------------
# PluginManager - Registration tests
# ---------------------------------------------------------------------------

class TestPluginManagerRegistration:
    def test_register_plugin(self):
        class MyPlugin:
            name = "manual-plugin"
            version = "0.1.0"
            plugin_type = "analyzer"
            def initialize(self, config): pass
            def execute(self, context): return {"ok": True}

        manager = PluginManager(plugin_dirs=[])
        manager.register(MyPlugin())
        metas = manager.list_plugins()
        names = {m.name for m in metas}
        assert "manual-plugin" in names

    def test_unregister_plugin(self):
        class RemovablePlugin:
            name = "removable"
            version = "0.1.0"
            plugin_type = "analyzer"
            def initialize(self, config): pass
            def execute(self, context): return {}

        manager = PluginManager(plugin_dirs=[])
        manager.register(RemovablePlugin())
        assert any(m.name == "removable" for m in manager.list_plugins())
        manager.unregister("removable")
        # After unregistration, plugin is no longer listed
        assert not any(m.name == "removable" for m in manager.list_plugins())


# ---------------------------------------------------------------------------
# PluginManager - Execution tests
# ---------------------------------------------------------------------------

class TestPluginManagerExecution:
    def test_execute_scenario_plugin(self, tmp_path: Path):
        _write_sample_plugin(tmp_path, "exec-plugin")
        manager = PluginManager(plugin_dirs=[tmp_path])

        from faultray.model.demo import create_demo_graph

        ctx = PluginContext(graph=create_demo_graph())
        result = manager.execute("exec-plugin", ctx)
        assert isinstance(result, list)
        assert len(result) > 0

    def test_execute_with_no_graph(self, tmp_path: Path):
        _write_sample_plugin(tmp_path, "no-graph-plugin")
        manager = PluginManager(plugin_dirs=[tmp_path])
        ctx = PluginContext()
        result = manager.execute("no-graph-plugin", ctx)
        assert isinstance(result, list)
        assert len(result) == 0

    def test_execute_disabled_raises(self, tmp_path: Path):
        _write_sample_plugin(tmp_path, "disabled-plugin")
        manager = PluginManager(plugin_dirs=[tmp_path])
        manager.load("disabled-plugin")
        manager.disable("disabled-plugin")
        with pytest.raises(RuntimeError, match="disabled"):
            manager.execute("disabled-plugin", PluginContext())


# ---------------------------------------------------------------------------
# PluginManager - Enable/Disable tests
# ---------------------------------------------------------------------------

class TestPluginManagerEnableDisable:
    def test_disable_and_enable(self, tmp_path: Path):
        _write_sample_plugin(tmp_path, "toggle-plugin")
        manager = PluginManager(plugin_dirs=[tmp_path])
        manager.load("toggle-plugin")

        manager.disable("toggle-plugin")
        metas = {m.name: m for m in manager.list_plugins()}
        assert metas["toggle-plugin"].enabled is False

        manager.enable("toggle-plugin")
        metas = {m.name: m for m in manager.list_plugins()}
        assert metas["toggle-plugin"].enabled is True


# ---------------------------------------------------------------------------
# PluginManager - Hot-reload tests
# ---------------------------------------------------------------------------

class TestPluginManagerReload:
    def test_reload_updates_plugin(self, tmp_path: Path):
        plugin_file = tmp_path / "reloadable.py"
        plugin_file.write_text(textwrap.dedent('''\
            PLUGIN_METADATA = {
                "name": "reloadable",
                "version": "1.0.0",
                "author": "Test",
                "description": "v1",
                "type": "scenario_generator",
            }

            class ReloadablePlugin:
                name = "reloadable"
                version = "1.0.0"
                plugin_type = "scenario_generator"
                def initialize(self, config): pass
                def execute(self, context): return [{"v": 1}]
        '''))

        manager = PluginManager(plugin_dirs=[tmp_path])
        manager.load("reloadable")

        # Update the plugin file
        plugin_file.write_text(textwrap.dedent('''\
            PLUGIN_METADATA = {
                "name": "reloadable",
                "version": "2.0.0",
                "author": "Test",
                "description": "v2",
                "type": "scenario_generator",
            }

            class ReloadablePlugin:
                name = "reloadable"
                version = "2.0.0"
                plugin_type = "scenario_generator"
                def initialize(self, config): pass
                def execute(self, context): return [{"v": 2}]
        '''))

        manager.reload("reloadable")
        plugin = manager.load("reloadable")
        assert plugin.version == "2.0.0"
        result = plugin.execute(PluginContext())
        assert result == [{"v": 2}]

    def test_reload_unknown_raises(self):
        manager = PluginManager(plugin_dirs=[])
        with pytest.raises(KeyError, match="not found"):
            manager.reload("nonexistent")


# ---------------------------------------------------------------------------
# PluginManager - Scaffolding tests
# ---------------------------------------------------------------------------

class TestPluginManagerScaffolding:
    def test_create_template(self, tmp_path: Path):
        manager = PluginManager(plugin_dirs=[])
        path = manager.create_plugin_template(
            "my-custom-plugin",
            PluginType.SCENARIO_GENERATOR,
            output_dir=tmp_path,
        )
        assert path.exists()
        content = path.read_text()
        assert "PLUGIN_METADATA" in content
        assert "my-custom-plugin" in content
        assert "scenario_generator" in content
        assert "class MyCustomPluginPlugin" in content

    def test_create_all_types(self, tmp_path: Path):
        manager = PluginManager(plugin_dirs=[])
        for ptype in PluginType:
            path = manager.create_plugin_template(
                f"test-{ptype.value}",
                ptype,
                output_dir=tmp_path,
            )
            assert path.exists()
            content = path.read_text()
            assert ptype.value in content

    def test_created_template_is_loadable(self, tmp_path: Path):
        manager = PluginManager(plugin_dirs=[tmp_path])
        path = manager.create_plugin_template(
            "loadable-template",
            PluginType.ANALYZER,
            output_dir=tmp_path,
        )
        # Should be discoverable and loadable
        metas = manager.discover()
        assert any(m.name == "loadable-template" for m in metas)
        plugin = manager.load("loadable-template")
        assert plugin.name == "loadable-template"

    def test_create_default_dir(self, tmp_path: Path, monkeypatch):
        """Scaffold uses ~/.faultzero/plugins/ by default."""
        import faultray.plugins.plugin_manager as pm

        monkeypatch.setattr(pm, "_DEFAULT_PLUGIN_DIR", tmp_path / "default_plugins")
        manager = PluginManager(plugin_dirs=[])
        path = manager.create_plugin_template("default-dir", PluginType.REPORTER)
        assert path.parent == tmp_path / "default_plugins"
        assert path.exists()


# ---------------------------------------------------------------------------
# PluginManager - Listing / querying tests
# ---------------------------------------------------------------------------

class TestPluginManagerListing:
    def test_list_plugins(self, tmp_path: Path):
        _write_sample_plugin(tmp_path, "list-a")
        _write_analyzer_plugin(tmp_path, "list-b")
        manager = PluginManager(plugin_dirs=[tmp_path])
        metas = manager.list_plugins()
        assert len(metas) == 2

    def test_get_plugins_by_type(self, tmp_path: Path):
        _write_sample_plugin(tmp_path, "type-a")
        _write_analyzer_plugin(tmp_path, "type-b")
        manager = PluginManager(plugin_dirs=[tmp_path])
        scenarios = manager.get_plugins_by_type(PluginType.SCENARIO_GENERATOR)
        analyzers = manager.get_plugins_by_type(PluginType.ANALYZER)
        assert len(scenarios) == 1
        assert len(analyzers) == 1
        assert scenarios[0].name == "type-a"
        assert analyzers[0].name == "type-b"

    def test_get_plugins_by_type_empty(self, tmp_path: Path):
        _write_sample_plugin(tmp_path, "only-scenario")
        manager = PluginManager(plugin_dirs=[tmp_path])
        reporters = manager.get_plugins_by_type(PluginType.REPORTER)
        assert len(reporters) == 0
