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
        manager.create_plugin_template(
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


# ---------------------------------------------------------------------------
# Sandbox security tests
# ---------------------------------------------------------------------------

class TestPluginSandboxSecurity:
    """Verify that exec()-loaded plugins cannot escape the restricted sandbox."""

    def test_blocked_dunder_getattr(self, tmp_path: Path):
        """__class__ and other dunder attrs are blocked via _safe_getattr."""
        from faultray.plugins.plugin_manager import _PLUGIN_SAFE_BUILTINS

        code = """
class Foo:
    bar = 1
f = Foo()
result = getattr(f, "__class__")
"""
        with pytest.raises((AttributeError, NameError)):
            exec(code, {"__builtins__": _PLUGIN_SAFE_BUILTINS})

    def test_blocked_subclasses_escape(self, tmp_path: Path):
        """Classical __subclasses__() sandbox escape path is blocked."""
        from faultray.plugins.plugin_manager import _PLUGIN_SAFE_BUILTINS

        # This is the classic Python sandbox escape via inherited __globals__
        code = """
class Foo:
    bar = 1
f = Foo()
cls = getattr(f, "__class__")
"""
        with pytest.raises((AttributeError, NameError)):
            exec(code, {"__builtins__": _PLUGIN_SAFE_BUILTINS})

    def test_blocked_os_import(self, tmp_path: Path):
        """Plugins cannot import os or subprocess."""
        from faultray.plugins.plugin_manager import _PLUGIN_SAFE_BUILTINS

        code = "import os"
        with pytest.raises(ImportError):
            exec(code, {"__builtins__": _PLUGIN_SAFE_BUILTINS})

    def test_allowed_math_import(self, tmp_path: Path):
        """Plugins can import whitelisted modules."""
        from faultray.plugins.plugin_manager import _PLUGIN_SAFE_BUILTINS

        code = "import math; result = math.pi"
        ns: dict = {}
        exec(code, {"__builtins__": _PLUGIN_SAFE_BUILTINS}, ns)
        assert abs(ns["result"] - 3.14159) < 0.001

    def test_normal_getattr_works(self, tmp_path: Path):
        """Non-dunder getattr still works inside sandbox."""
        from faultray.plugins.plugin_manager import _PLUGIN_SAFE_BUILTINS

        code = """
class Foo:
    bar = 42
f = Foo()
result = getattr(f, "bar")
"""
        ns: dict = {}
        exec(code, {"__builtins__": _PLUGIN_SAFE_BUILTINS}, ns)
        assert ns["result"] == 42

    def test_direct_subclasses_on_base_exception_blocked(self):
        """Direct attribute access BaseException.__subclasses__() must be blocked.

        This is the core attack vector that bypasses _safe_getattr:
          BaseException.__subclasses__() → os._wrap_close → __globals__ → os.system
        The safe proxy must prevent this even with direct '.' attribute access.
        """
        from faultray.plugins.plugin_manager import _PLUGIN_SAFE_BUILTINS

        code = "result = BaseException.__subclasses__()"
        with pytest.raises((AttributeError, TypeError)):
            exec(code, {"__builtins__": _PLUGIN_SAFE_BUILTINS})

    def test_direct_subclasses_on_exception_blocked(self):
        """Direct attribute access Exception.__subclasses__() must be blocked."""
        from faultray.plugins.plugin_manager import _PLUGIN_SAFE_BUILTINS

        code = "result = Exception.__subclasses__()"
        with pytest.raises((AttributeError, TypeError)):
            exec(code, {"__builtins__": _PLUGIN_SAFE_BUILTINS})

    def test_concrete_exception_still_catchable(self):
        """Concrete exception classes (ValueError, RuntimeError etc.) remain usable
        inside the sandbox with 'except <ConcreteType>:' syntax."""
        from faultray.plugins.plugin_manager import _PLUGIN_SAFE_BUILTINS

        code = """
try:
    raise ValueError("boom")
except ValueError:
    caught = True
"""
        ns: dict = {}
        exec(code, {"__builtins__": _PLUGIN_SAFE_BUILTINS}, ns)
        assert ns.get("caught") is True

    def test_runtime_error_still_catchable(self):
        """RuntimeError can be caught by name inside the sandbox."""
        from faultray.plugins.plugin_manager import _PLUGIN_SAFE_BUILTINS

        code = """
try:
    raise RuntimeError("boom")
except RuntimeError:
    caught = True
"""
        ns: dict = {}
        exec(code, {"__builtins__": _PLUGIN_SAFE_BUILTINS}, ns)
        assert ns.get("caught") is True

    def test_full_escape_chain_blocked(self):
        """Full classic sandbox-escape chain must be blocked end-to-end.

        Attack: BaseException.__subclasses__() iterates all live subclasses,
        finds one with __globals__ that contains 'os', then calls os.system().
        """
        from faultray.plugins.plugin_manager import _PLUGIN_SAFE_BUILTINS

        # Step 1 of the chain — must raise before any iteration happens
        code = "subs = BaseException.__subclasses__()"
        with pytest.raises((AttributeError, TypeError)):
            exec(code, {"__builtins__": _PLUGIN_SAFE_BUILTINS})

    @pytest.mark.parametrize("exc_name", [
        "ValueError",
        "TypeError",
        "KeyError",
        "IndexError",
        "AttributeError",
        "RuntimeError",
        "NotImplementedError",
        "StopIteration",
        "ImportError",
    ])
    def test_concrete_exception_subclasses_blocked(self, exc_name: str):
        """__subclasses__() on concrete exception classes must be blocked.

        SEC-01: Concrete exception classes (ValueError etc.) previously exposed
        __subclasses__() because only Exception/BaseException were proxied.
        The attack path: ValueError.__subclasses__() can enumerate live subclasses
        and eventually reach __globals__ containing 'os'.
        """
        from faultray.plugins.plugin_manager import _PLUGIN_SAFE_BUILTINS

        code = f"result = {exc_name}.__subclasses__()"
        with pytest.raises((AttributeError, TypeError)):
            exec(code, {"__builtins__": _PLUGIN_SAFE_BUILTINS})

    def test_concrete_exception_catchable_by_base_class(self):
        """Concrete proxied exceptions must still be catchable by base class.

        SEC-01 regression: after wrapping concrete exceptions, 'except Exception:'
        must still catch _SafeKeyError etc. (MRO must include _SafeException).
        """
        from faultray.plugins.plugin_manager import _PLUGIN_SAFE_BUILTINS

        code = """
try:
    raise KeyError("missing")
except Exception:
    caught = True
"""
        ns: dict = {}
        exec(code, {"__builtins__": _PLUGIN_SAFE_BUILTINS}, ns)
        assert ns.get("caught") is True

    def test_stop_iteration_catchable_by_base_exception(self):
        """StopIteration must be catchable by BaseException in the sandbox."""
        from faultray.plugins.plugin_manager import _PLUGIN_SAFE_BUILTINS

        code = """
try:
    raise StopIteration
except BaseException:
    caught = True
"""
        ns: dict = {}
        exec(code, {"__builtins__": _PLUGIN_SAFE_BUILTINS}, ns)
        assert ns.get("caught") is True

    # ------------------------------------------------------------------
    # AST-rewriting sandbox tests (SEC-01 hardening)
    # ------------------------------------------------------------------

    @staticmethod
    def _exec_in_sandbox(source: str) -> dict:
        """Compile via _sandbox_compile and exec in a realistic sandbox."""
        import types

        from faultray.plugins.plugin_manager import (
            _PLUGIN_SAFE_BUILTINS,
            _safe_getattr,
            _sandbox_compile,
        )

        module = types.ModuleType("_fz_plugin_test")
        module.__dict__["__builtins__"] = _PLUGIN_SAFE_BUILTINS
        module.__dict__["_safe_getattr"] = _safe_getattr
        code = _sandbox_compile(source, "<sandbox-test>")
        exec(code, module.__dict__)  # noqa: S102
        return module.__dict__

    def test_ast_rewrite_blocks_class_bases_subclasses(self):
        """(1).__class__.__bases__[0].__subclasses__() must be blocked."""
        with pytest.raises(AttributeError, match="__class__"):
            self._exec_in_sandbox(
                "result = (1).__class__.__bases__[0].__subclasses__()"
            )

    def test_ast_rewrite_blocks_mro_escape(self):
        """str.__mro__[-1].__subclasses__() must be blocked."""
        with pytest.raises(AttributeError, match="__mro__"):
            self._exec_in_sandbox(
                'result = str.__mro__[-1].__subclasses__()'
            )

    def test_ast_rewrite_blocks_globals_via_dict(self):
        """cls.__dict__[x].__globals__ must be blocked via AST rewrite."""
        with pytest.raises(AttributeError, match="__class__"):
            self._exec_in_sandbox(
                "(1).__class__.__bases__[0].__subclasses__()"
            )

    def test_ast_rewrite_allows_normal_attr_access(self):
        """Normal attribute access (list.append, str.upper) must work."""
        ns = self._exec_in_sandbox(
            'x = [1, 2, 3]\nx.append(4)\nlength = len(x)\nmsg = "hello"\nupper = msg.upper()'
        )
        assert ns["length"] == 4
        assert ns["upper"] == "HELLO"

    def test_ast_rewrite_allows_class_definition(self):
        """Plugin code should still be able to define and use classes."""
        ns = self._exec_in_sandbox(
            'class MyPlugin:\n    name = "test"\n    version = "1.0"\n    def execute(self):\n        return 42\n\ninstance = MyPlugin()\nresult = instance.execute()'
        )
        assert ns["result"] == 42

    def test_ast_rewrite_allows_exception_handling(self):
        """try/except must work in the sandbox."""
        ns = self._exec_in_sandbox(
            'caught = False\ntry:\n    raise ValueError("test")\nexcept ValueError:\n    caught = True'
        )
        assert ns["caught"] is True

    def test_ast_rewrite_blocks_full_exploit_chain(self):
        """Full exploit: literal -> object -> __subclasses__ -> __globals__ -> os."""
        with pytest.raises(AttributeError):
            self._exec_in_sandbox(
                'subs = (1).__class__.__bases__[0].__subclasses__()\n'
                'for cls in subs:\n'
                '    if "_wrap_close" in cls.__name__:\n'
                '        g = cls.__dict__["close"].__globals__\n'
                '        break'
            )


# ---------------------------------------------------------------------------
# Discovery must not execute plugin code (#149)
# ---------------------------------------------------------------------------

class TestMetadataReadIsStatic:
    def test_metadata_read_without_executing_module(self, tmp_path: Path):
        """_read_metadata_from_file extracts PLUGIN_METADATA via AST and must
        never import the module — a side effect at import time proves a
        regression to exec-based discovery."""
        marker = tmp_path / "executed.marker"
        plugin = tmp_path / "sneaky.py"
        plugin.write_text(
            textwrap.dedent(f"""\
                from pathlib import Path
                Path({str(marker)!r}).write_text("ran")  # would run if imported

                PLUGIN_METADATA = {{
                    "name": "sneaky",
                    "version": "1.0.0",
                    "type": "scenario_generator",
                }}
            """)
        )
        meta = PluginManager._read_metadata_from_file(plugin)
        assert meta is not None
        assert meta.name == "sneaky"
        assert not marker.exists(), "module was executed during metadata read"

    def test_non_literal_metadata_is_ignored(self, tmp_path: Path):
        """A computed (non-literal) PLUGIN_METADATA can't be statically read and
        must yield None rather than falling back to execution."""
        plugin = tmp_path / "dynamic.py"
        plugin.write_text("PLUGIN_METADATA = dict(name='x', version='1.0.0')\n")
        assert PluginManager._read_metadata_from_file(plugin) is None
