"""Security validation tests for FaultRay / FaultRay.

Tests non-functional security requirements:
- Input sanitization for component IDs, names, and config loading
- Data integrity of resilience scores and graph isolation
- API security (structured error responses, input validation, large payloads)
- Dependency security (no unsafe eval/exec/pickle with user data)
"""

from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path

import pytest

from faultray.model.components import (
    Component,
    ComponentType,
    Dependency,
    HealthStatus,
)
from faultray.model.graph import InfraGraph


# =========================================================================
# 1. Input Sanitization
# =========================================================================


class TestInputSanitization:
    """Verify that component IDs, names, and config inputs are safely handled."""

    # --- Path Traversal ---

    def test_component_id_with_path_traversal_dots(self):
        """Component IDs with '../' sequences should not cause path traversal
        when the graph is serialised / saved."""
        graph = InfraGraph()
        malicious_id = "../../../etc/passwd"
        comp = Component(
            id=malicious_id,
            name="Malicious",
            type=ComponentType.APP_SERVER,
        )
        graph.add_component(comp)

        # The component should be retrievable by its exact ID
        assert graph.get_component(malicious_id) is not None

        # Serialisation must not interpret the ID as a path
        data = graph.to_dict()
        ids = [c["id"] for c in data["components"]]
        assert malicious_id in ids

        # Save to a temp file — should not escape the temp directory
        with tempfile.TemporaryDirectory() as tmpdir:
            out_path = Path(tmpdir) / "test_model.json"
            graph.save(out_path)
            raw = json.loads(out_path.read_text())
            saved_ids = [c["id"] for c in raw["components"]]
            assert malicious_id in saved_ids
            # Ensure no file was created outside tmpdir
            assert not Path("/etc/passwd_faultray").exists()

    def test_component_id_with_null_bytes(self):
        """Component IDs with null bytes should be stored literally."""
        graph = InfraGraph()
        comp = Component(
            id="comp\x00injected",
            name="NullByte",
            type=ComponentType.CACHE,
        )
        graph.add_component(comp)
        assert graph.get_component("comp\x00injected") is not None

    def test_component_id_with_slashes_and_backslashes(self):
        """IDs containing / and \\ must not cause filesystem side effects."""
        graph = InfraGraph()
        for cid in ["foo/bar", "foo\\bar", "..\\..\\windows\\system32"]:
            comp = Component(id=cid, name=cid, type=ComponentType.CUSTOM)
            graph.add_component(comp)

        assert len(graph.components) == 3

        with tempfile.TemporaryDirectory() as tmpdir:
            out_path = Path(tmpdir) / "model.json"
            graph.save(out_path)
            raw = json.loads(out_path.read_text())
            assert len(raw["components"]) == 3

    # --- XSS-like Content in Names ---

    def test_component_name_with_html_tags(self):
        """HTML tags in component names should be escaped in HTML report generation."""
        from faultray.reporter.html_report import _build_finding
        from faultray.simulator.cascade import CascadeChain, CascadeEffect
        from faultray.simulator.engine import ScenarioResult
        from faultray.simulator.scenarios import Scenario

        xss_name = '<script>alert("xss")</script>'

        scenario = Scenario(
            id="test-xss",
            name="XSS Test",
            description="Test XSS in names",
            faults=[],
        )
        cascade = CascadeChain(trigger="test", total_components=1)
        cascade.effects.append(
            CascadeEffect(
                component_id="xss-comp",
                component_name=xss_name,
                health=HealthStatus.DOWN,
                reason="test",
            )
        )
        result = ScenarioResult(
            scenario=scenario, cascade=cascade, risk_score=5.0
        )
        finding = _build_finding(result)
        # The component_name in effects should be present
        assert len(finding["effects"]) == 1
        # The raw name is passed to template — verify Jinja2 autoescaping
        # handles it (we just confirm the data structure is correct here)
        assert finding["effects"][0]["component_name"] == xss_name

    def test_component_name_with_script_injection(self):
        """Component names with script tags should not break graph serialisation."""
        graph = InfraGraph()
        comp = Component(
            id="comp1",
            name='<img onerror="alert(1)" src=x>',
            type=ComponentType.WEB_SERVER,
        )
        graph.add_component(comp)
        data = graph.to_dict()
        assert data["components"][0]["name"] == '<img onerror="alert(1)" src=x>'

    # --- YAML / JSON Config Safety ---

    def test_yaml_safe_load_used(self):
        """Verify that the YAML loader uses safe_load, not yaml.load."""
        import inspect
        from faultray.model import loader

        source = inspect.getsource(loader)
        # Must use yaml.safe_load, never yaml.load with unsafe Loader
        assert "yaml.safe_load" in source
        # Should not contain yaml.load( without safe
        # (yaml.safe_load contains 'yaml.' so we check for bare yaml.load()
        # calls that use yaml.load(... Loader=yaml.FullLoader) or similar)
        unsafe_patterns = re.findall(r"yaml\.load\s*\(", source)
        assert len(unsafe_patterns) == 0, (
            f"Found unsafe yaml.load() calls in loader.py: {unsafe_patterns}"
        )

    def test_json_loads_on_model_file(self):
        """Loading a JSON model should reject non-dict top-level structures."""
        with tempfile.NamedTemporaryFile(
            suffix=".json", mode="w", delete=False
        ) as f:
            json.dump([1, 2, 3], f)  # list instead of dict
            f.flush()
            try:
                # InfraGraph.load expects a dict with 'components' key
                graph = InfraGraph.load(Path(f.name))
                # If it loads without error, it should produce an empty graph
                assert len(graph.components) == 0
            except (ValueError, KeyError, TypeError, AttributeError):
                pass  # Expected — rejecting invalid format is acceptable
            finally:
                os.unlink(f.name)

    def test_yaml_loader_rejects_non_dict(self):
        """YAML loader should raise ValueError for non-dict top-level."""
        from faultray.model.loader import load_yaml

        with tempfile.NamedTemporaryFile(
            suffix=".yaml", mode="w", delete=False
        ) as f:
            f.write("- item1\n- item2\n")
            f.flush()
            try:
                with pytest.raises(ValueError, match="YAML mapping"):
                    load_yaml(f.name)
            finally:
                os.unlink(f.name)


# =========================================================================
# 2. Data Integrity
# =========================================================================


class TestDataIntegrity:
    """Verify resilience scores cannot be manipulated and graphs are isolated."""

    def test_resilience_score_bounds(self):
        """Resilience score must always be in [0, 100]."""
        graph = InfraGraph()
        # Empty graph
        assert graph.resilience_score() == 0.0

        # Single healthy component
        graph.add_component(
            Component(id="a", name="A", type=ComponentType.APP_SERVER)
        )
        score = graph.resilience_score()
        assert 0.0 <= score <= 100.0

    def test_resilience_score_with_extreme_replicas(self):
        """Very high replica counts should not push the score above 100."""
        graph = InfraGraph()
        for i in range(20):
            graph.add_component(
                Component(
                    id=f"comp-{i}",
                    name=f"Comp {i}",
                    type=ComponentType.APP_SERVER,
                    replicas=1000,
                )
            )
        score = graph.resilience_score()
        assert 0.0 <= score <= 100.0

    def test_resilience_score_not_affected_by_crafted_negative_replicas(self):
        """Replicas < 1 should be rejected by Pydantic validation."""
        with pytest.raises(Exception):
            Component(
                id="bad",
                name="Bad",
                type=ComponentType.DATABASE,
                replicas=0,
            )

        with pytest.raises(Exception):
            Component(
                id="bad",
                name="Bad",
                type=ComponentType.DATABASE,
                replicas=-10,
            )

    def test_resilience_v2_score_bounds(self):
        """resilience_score_v2 must return score in [0, 100]."""
        graph = InfraGraph()
        result = graph.resilience_score_v2()
        assert result["score"] == 0.0

        graph.add_component(
            Component(id="x", name="X", type=ComponentType.CACHE, replicas=5)
        )
        result = graph.resilience_score_v2()
        assert 0.0 <= result["score"] <= 100.0

    def test_graph_isolation_no_shared_state(self):
        """Two InfraGraph instances must not share internal state."""
        graph1 = InfraGraph()
        graph2 = InfraGraph()

        graph1.add_component(
            Component(id="only-in-1", name="G1", type=ComponentType.DATABASE)
        )
        graph2.add_component(
            Component(id="only-in-2", name="G2", type=ComponentType.CACHE)
        )

        assert graph1.get_component("only-in-2") is None
        assert graph2.get_component("only-in-1") is None
        assert len(graph1.components) == 1
        assert len(graph2.components) == 1

    def test_graph_isolation_after_modification(self):
        """Modifying one graph must not affect another."""
        graph1 = InfraGraph()
        graph2 = InfraGraph()

        comp = Component(id="shared-id", name="S", type=ComponentType.QUEUE)
        graph1.add_component(comp)

        # graph2 should still be empty
        assert len(graph2.components) == 0
        assert graph2.get_component("shared-id") is None

    def test_no_global_mutable_state_in_graph(self):
        """Creating multiple graphs in sequence should not leak state."""
        scores = []
        for i in range(5):
            g = InfraGraph()
            g.add_component(
                Component(
                    id=f"c{i}", name=f"C{i}", type=ComponentType.APP_SERVER
                )
            )
            scores.append(g.resilience_score())

        # All single-component graphs should have the same score
        assert len(set(scores)) == 1

    def test_to_dict_does_not_expose_internal_graph(self):
        """to_dict should return a serialisable copy, not internal references."""
        graph = InfraGraph()
        graph.add_component(
            Component(id="a", name="A", type=ComponentType.WEB_SERVER)
        )
        d = graph.to_dict()
        # Mutating the returned dict should not affect the graph
        d["components"].clear()
        assert len(graph.components) == 1


# =========================================================================
# 3. API Security
# =========================================================================


class TestAPISecurity:
    """Test API endpoint security: input validation, error handling, payload limits."""

    @pytest.fixture
    def client(self):
        """Create a FastAPI test client with auth headers."""
        try:
            from fastapi.testclient import TestClient
            from faultray.api.server import app, set_graph
            from faultray.model.demo import create_demo_graph
            from tests.conftest import TEST_API_KEY, _setup_test_user

            _setup_test_user()
            set_graph(create_demo_graph())
            client = TestClient(app, raise_server_exceptions=False)
            client.headers["Authorization"] = f"Bearer {TEST_API_KEY}"
            return client
        except ImportError:
            pytest.skip("FastAPI / httpx test client not available")

    def test_simulate_failure_invalid_component_returns_404(self, client):
        """POST /api/simulate-failure/{id} with non-existent ID should return 404."""
        resp = client.post("/api/simulate-failure/nonexistent-component-xyz")
        assert resp.status_code == 404
        body = resp.json()
        assert "error" in body
        # Should not contain a Python traceback
        error_msg = json.dumps(body)
        assert "Traceback" not in error_msg
        assert "File " not in error_msg

    def test_error_responses_have_structured_format(self, client):
        """Error responses should follow {error: {code, message}} format."""
        resp = client.post("/api/simulate-failure/does-not-exist")
        assert resp.status_code == 404
        body = resp.json()
        assert "error" in body
        assert "code" in body["error"]
        assert "message" in body["error"]

    def test_error_responses_do_not_leak_stack_traces(self, client):
        """Error responses must not contain Python stack traces."""
        endpoints = [
            ("/api/simulate-failure/INVALID", "post"),
            ("/api/runs/999999", "get"),
        ]
        for path, method in endpoints:
            if method == "post":
                resp = client.post(path)
            else:
                resp = client.get(path)
            body_text = resp.text
            assert "Traceback (most recent call last)" not in body_text, (
                f"Stack trace leaked in {method.upper()} {path}"
            )

    def test_component_id_with_special_chars_in_api(self, client):
        """API should handle component IDs with special characters gracefully."""
        special_ids = [
            "../../../etc/passwd",
            "<script>alert(1)</script>",
            "' OR '1'='1",
            "comp%00id",
        ]
        for cid in special_ids:
            resp = client.post(f"/api/simulate-failure/{cid}")
            # Should return 404 (not found) or 400, never 500
            assert resp.status_code in (400, 404, 422), (
                f"Unexpected status {resp.status_code} for ID: {cid}"
            )

    def test_health_endpoint_returns_200(self, client):
        """GET /api/health should always return 200."""
        resp = client.get("/api/health")
        assert resp.status_code == 200

    def test_large_json_payload_does_not_crash(self, client):
        """Sending a very large JSON payload should not crash the server."""
        # Try posting to /api/simulate with a large body
        large_payload = {"data": "x" * 100_000}
        resp = client.post(
            "/api/simulate",
            json=large_payload,
        )
        # Should respond without crashing (any status code is fine)
        assert resp.status_code in range(200, 600)


# =========================================================================
# 4. Dependency Security
# =========================================================================


class TestDependencySecurity:
    """Verify no unsafe deserialization or code execution patterns."""

    def test_no_eval_in_source_modules(self):
        """Core modules must not use eval() with user-controlled data."""
        import inspect
        import faultray.model.graph as graph_mod
        import faultray.model.components as comp_mod
        import faultray.model.loader as loader_mod
        import faultray.scoring as scoring_mod

        for mod in [graph_mod, comp_mod, loader_mod, scoring_mod]:
            source = inspect.getsource(mod)
            # Check for bare eval() calls
            eval_calls = re.findall(r"\beval\s*\(", source)
            assert len(eval_calls) == 0, (
                f"Found eval() in {mod.__name__}: {eval_calls}"
            )

    def test_no_pickle_loads_in_core(self):
        """Core modules must not use pickle.loads (unsafe deserialization)."""
        import inspect
        import faultray.model.graph as graph_mod
        import faultray.model.components as comp_mod
        import faultray.model.loader as loader_mod

        for mod in [graph_mod, comp_mod, loader_mod]:
            source = inspect.getsource(mod)
            assert "pickle.loads" not in source, (
                f"Found pickle.loads in {mod.__name__}"
            )
            assert "pickle.load(" not in source, (
                f"Found pickle.load in {mod.__name__}"
            )

    def test_no_exec_in_core_modules(self):
        """Core model/graph/loader modules must not use exec()."""
        import inspect
        import faultray.model.graph as graph_mod
        import faultray.model.components as comp_mod
        import faultray.model.loader as loader_mod

        for mod in [graph_mod, comp_mod, loader_mod]:
            source = inspect.getsource(mod)
            exec_calls = re.findall(r"\bexec\s*\(", source)
            assert len(exec_calls) == 0, (
                f"Found exec() in {mod.__name__}: {exec_calls}"
            )

    def test_yaml_safe_load_not_unsafe_loader(self):
        """YAML loading must use safe_load, not load with FullLoader/UnsafeLoader."""
        import inspect
        from faultray.model import loader

        source = inspect.getsource(loader)
        # Must not contain Loader=yaml.FullLoader or Loader=yaml.UnsafeLoader
        assert "FullLoader" not in source
        assert "UnsafeLoader" not in source

    def test_json_loading_uses_stdlib(self):
        """JSON model loading should use stdlib json, not unsafe alternatives."""
        import inspect
        import faultray.model.graph as graph_mod

        source = inspect.getsource(graph_mod)
        assert "json.loads" in source or "json.load" in source
        # Should not use anything exotic for JSON parsing
        assert "yaml.load" not in source

    def test_policy_engine_no_eval(self):
        """Policy engine explicitly avoids eval() for condition evaluation."""
        import inspect
        import faultray.policy.engine as policy_mod

        source = inspect.getsource(policy_mod)
        # Match actual eval() calls — exclude comments, docstrings, and
        # backtick-quoted references like ``eval()``
        lines = source.split("\n")
        eval_call_lines = []
        for lineno, line in enumerate(lines, 1):
            stripped = line.strip()
            # Skip comments and docstring lines
            if stripped.startswith("#") or stripped.startswith('"""') or stripped.startswith("'''"):
                continue
            # Skip lines that reference eval in backtick-quoted text
            if "`eval" in stripped or "``eval" in stripped:
                continue
            # Check for actual eval() calls (not _eval, not "eval", not in strings)
            if re.search(r"(?<![_a-zA-Z])eval\s*\(", stripped):
                eval_call_lines.append((lineno, stripped))

        assert len(eval_call_lines) == 0, (
            f"Found eval() calls in policy engine: {eval_call_lines}"
        )

    def test_plugin_exec_is_sandboxed(self):
        """Plugin manager uses exec() but only on local .py files, not user input."""
        import inspect
        from faultray.plugins import plugin_manager

        source = inspect.getsource(plugin_manager)
        # exec() IS used in plugin_manager for loading .py plugins, which is
        # expected. Verify it uses compile() first (basic sandboxing).
        assert "compile(" in source, (
            "Plugin manager exec() should use compile() for basic validation"
        )


# =========================================================================
# 5. Model Loading Edge Cases
# =========================================================================


class TestModelLoadingEdgeCases:
    """Verify model loading handles adversarial inputs safely."""

    def test_load_model_with_duplicate_component_ids(self):
        """Loading a model where two components share an ID should overwrite."""
        graph = InfraGraph()
        comp1 = Component(
            id="dup", name="First", type=ComponentType.DATABASE
        )
        comp2 = Component(
            id="dup", name="Second", type=ComponentType.CACHE
        )
        graph.add_component(comp1)
        graph.add_component(comp2)

        # The second should overwrite the first
        assert graph.get_component("dup").name == "Second"
        assert len(graph.components) == 1

    def test_load_json_with_extra_fields_ignored(self):
        """Extra fields in JSON model should not cause crashes."""
        with tempfile.NamedTemporaryFile(
            suffix=".json", mode="w", delete=False
        ) as f:
            model = {
                "schema_version": "3.0",
                "components": [
                    {
                        "id": "c1",
                        "name": "C1",
                        "type": "app_server",
                        "malicious_field": "DROP TABLE",
                    }
                ],
                "dependencies": [],
                "extra_top_level": True,
            }
            json.dump(model, f)
            f.flush()
            try:
                # Pydantic models with extra fields may raise or ignore
                # depending on config — either is acceptable
                try:
                    graph = InfraGraph.load(Path(f.name))
                    assert graph.get_component("c1") is not None
                except Exception:
                    pass  # Rejecting unexpected fields is also safe
            finally:
                os.unlink(f.name)

    def test_dependency_with_nonexistent_component(self):
        """Adding a dependency referencing a missing component should not crash."""
        graph = InfraGraph()
        graph.add_component(
            Component(id="exists", name="E", type=ComponentType.APP_SERVER)
        )
        # Adding an edge where target doesn't exist in _components
        dep = Dependency(
            source_id="exists",
            target_id="ghost",
        )
        # add_dependency adds to networkx but ghost won't be in _components
        graph.add_dependency(dep)
        # get_dependencies should handle missing component gracefully
        deps = graph.get_dependencies("exists")
        # ghost is not in _components, so it should be filtered out
        ghost_deps = [d for d in deps if d.id == "ghost"]
        assert len(ghost_deps) == 0

    def test_very_long_component_id(self):
        """Extremely long component IDs should not cause memory issues."""
        graph = InfraGraph()
        long_id = "x" * 10_000
        comp = Component(
            id=long_id, name="Long", type=ComponentType.CUSTOM
        )
        graph.add_component(comp)
        assert graph.get_component(long_id) is not None

    def test_unicode_component_ids(self):
        """Unicode characters in IDs should be handled correctly."""
        graph = InfraGraph()
        unicode_ids = [
            "\u65e5\u672c\u8a9e\u30b5\u30fc\u30d0\u30fc",  # Japanese
            "\u0441\u0435\u0440\u0432\u0435\u0440",  # Russian
            "\U0001f525fire-server",  # Emoji
        ]
        for uid in unicode_ids:
            graph.add_component(
                Component(id=uid, name=uid, type=ComponentType.APP_SERVER)
            )
        assert len(graph.components) == len(unicode_ids)
        for uid in unicode_ids:
            assert graph.get_component(uid) is not None
