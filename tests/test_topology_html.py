"""Tests for Interactive HTML Topology Map Generator (Feature F)."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from faultray.model.components import (
    CircuitBreakerConfig,
    Component,
    ComponentType,
    Dependency,
)
from faultray.model.graph import InfraGraph
from faultray.reporter.topology_html import generate_topology_html


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_simple_graph() -> InfraGraph:
    g = InfraGraph()
    g.add_component(Component(id="lb", name="Load Balancer", type=ComponentType.LOAD_BALANCER, replicas=2))
    g.add_component(Component(id="app", name="App Server", type=ComponentType.APP_SERVER, replicas=3))
    g.add_component(Component(id="db", name="PostgreSQL", type=ComponentType.DATABASE, replicas=1))
    g.add_dependency(Dependency(source_id="lb", target_id="app", dependency_type="requires", weight=1.0))
    g.add_dependency(Dependency(source_id="app", target_id="db", dependency_type="requires", weight=1.0))
    return g


def _make_diverse_graph() -> InfraGraph:
    """Graph with multiple component types and edge types for thorough tests."""
    g = InfraGraph()
    g.add_component(Component(id="lb", name="NGINX LB", type=ComponentType.LOAD_BALANCER, replicas=2, owner="infra-team"))
    g.add_component(Component(id="app", name="API Server", type=ComponentType.APP_SERVER, replicas=3))
    g.add_component(Component(id="cache", name="Redis", type=ComponentType.CACHE, replicas=2))
    g.add_component(Component(id="db", name="Postgres", type=ComponentType.DATABASE, replicas=2))
    g.add_component(Component(id="stripe", name="Stripe API", type=ComponentType.EXTERNAL_API, host="api.stripe.com"))
    g.add_component(Component(id="queue", name="RabbitMQ", type=ComponentType.QUEUE, replicas=1))
    g.add_dependency(Dependency(source_id="lb", target_id="app", dependency_type="requires", weight=1.0))
    g.add_dependency(Dependency(source_id="app", target_id="db", dependency_type="requires", weight=0.9))
    g.add_dependency(Dependency(source_id="app", target_id="cache", dependency_type="optional", weight=0.5))
    g.add_dependency(Dependency(source_id="app", target_id="stripe", dependency_type="requires", weight=0.8))
    g.add_dependency(Dependency(source_id="app", target_id="queue", dependency_type="async", weight=0.3))
    return g


def _generate_and_read(graph: InfraGraph) -> str:
    """Generate HTML to temp file and return its content."""
    with tempfile.TemporaryDirectory() as tmpdir:
        out = Path(tmpdir) / "topology.html"
        generate_topology_html(graph, out)
        return out.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Basic structure tests
# ---------------------------------------------------------------------------

class TestGenerateTopologyHtml:
    def test_creates_file(self) -> None:
        g = _make_simple_graph()
        with tempfile.TemporaryDirectory() as tmpdir:
            out = Path(tmpdir) / "topology.html"
            generate_topology_html(g, out)
            assert out.exists()

    def test_file_is_not_empty(self) -> None:
        g = _make_simple_graph()
        html = _generate_and_read(g)
        assert len(html) > 1000

    def test_html_doctype(self) -> None:
        g = _make_simple_graph()
        html = _generate_and_read(g)
        assert "<!DOCTYPE html>" in html

    def test_d3_cdn_link_present(self) -> None:
        g = _make_simple_graph()
        html = _generate_and_read(g)
        assert "d3js.org/d3.v7.min.js" in html

    def test_creates_parent_dirs(self) -> None:
        g = _make_simple_graph()
        with tempfile.TemporaryDirectory() as tmpdir:
            out = Path(tmpdir) / "subdir" / "deep" / "topology.html"
            generate_topology_html(g, out)
            assert out.exists()

    def test_title_in_html(self) -> None:
        g = _make_simple_graph()
        html = _generate_and_read(g)
        assert "<title>" in html
        assert "FaultRay" in html


# ---------------------------------------------------------------------------
# Node data tests
# ---------------------------------------------------------------------------

class TestNodeData:
    def _extract_nodes(self, graph: InfraGraph) -> list[dict]:
        html = _generate_and_read(graph)
        # Find the NODES = [...] assignment
        start = html.index("const NODES = ") + len("const NODES = ")
        end = html.index(";\n    const EDGES", start)
        return json.loads(html[start:end])

    def test_node_count_matches_components(self) -> None:
        g = _make_simple_graph()
        nodes = self._extract_nodes(g)
        assert len(nodes) == 3

    def test_node_has_required_fields(self) -> None:
        g = _make_simple_graph()
        nodes = self._extract_nodes(g)
        required = {"id", "name", "type", "replicas", "owner", "health", "color", "health_color", "size"}
        for node in nodes:
            assert required.issubset(node.keys()), f"Missing fields in node: {node.keys()}"

    def test_node_ids_match_component_ids(self) -> None:
        g = _make_simple_graph()
        nodes = self._extract_nodes(g)
        node_ids = {n["id"] for n in nodes}
        assert node_ids == {"lb", "app", "db"}

    def test_node_size_larger_for_more_dependents(self) -> None:
        g = _make_simple_graph()
        nodes = self._extract_nodes(g)
        node_map = {n["id"]: n for n in nodes}
        # lb has 0 dependents, app has 1 (lb depends on app), db has 1 (app depends on db)
        # lb -> app -> db; app has lb as dependent, db has app as dependent
        # lb's dependents: none (nothing depends on lb)
        # The size is based on dependents (things that depend ON this node)
        assert node_map["lb"]["size"] >= 12  # baseline
        assert node_map["app"]["size"] >= node_map["lb"]["size"]  # app has more dependents

    def test_external_api_node_has_correct_type(self) -> None:
        g = _make_diverse_graph()
        nodes = self._extract_nodes(g)
        stripe_node = next(n for n in nodes if n["id"] == "stripe")
        assert stripe_node["type"] == "external_api"

    def test_node_color_is_hex(self) -> None:
        g = _make_simple_graph()
        nodes = self._extract_nodes(g)
        for node in nodes:
            assert node["color"].startswith("#"), f"Node color should be hex: {node['color']}"


# ---------------------------------------------------------------------------
# Edge data tests
# ---------------------------------------------------------------------------

class TestEdgeData:
    def _extract_edges(self, graph: InfraGraph) -> list[dict]:
        html = _generate_and_read(graph)
        start = html.index("const EDGES = ") + len("const EDGES = ")
        end = html.index(";\n    const LEGEND", start)
        return json.loads(html[start:end])

    def test_edge_count_matches_dependencies(self) -> None:
        g = _make_simple_graph()
        edges = self._extract_edges(g)
        assert len(edges) == 2

    def test_edge_has_required_fields(self) -> None:
        g = _make_simple_graph()
        edges = self._extract_edges(g)
        required = {"source", "target", "type", "weight", "color", "stroke_width"}
        for edge in edges:
            assert required.issubset(edge.keys())

    def test_requires_edge_is_red(self) -> None:
        g = _make_diverse_graph()
        edges = self._extract_edges(g)
        req_edges = [e for e in edges if e["type"] == "requires"]
        assert all(e["color"] == "#e15759" for e in req_edges)

    def test_optional_edge_is_yellow(self) -> None:
        g = _make_diverse_graph()
        edges = self._extract_edges(g)
        opt_edges = [e for e in edges if e["type"] == "optional"]
        assert all(e["color"] == "#edc948" for e in opt_edges)

    def test_async_edge_is_gray(self) -> None:
        g = _make_diverse_graph()
        edges = self._extract_edges(g)
        async_edges = [e for e in edges if e["type"] == "async"]
        assert all(e["color"] == "#bab0ac" for e in async_edges)

    def test_edge_stroke_width_scales_with_weight(self) -> None:
        g = _make_diverse_graph()
        edges = self._extract_edges(g)
        edge_map = {(e["source"], e["target"]): e for e in edges}
        # requires(app->db, weight=0.9) should be thicker than async(app->queue, weight=0.3)
        req_edge = edge_map.get(("app", "db"))
        async_edge = edge_map.get(("app", "queue"))
        if req_edge and async_edge:
            assert req_edge["stroke_width"] > async_edge["stroke_width"]


# ---------------------------------------------------------------------------
# Legend tests
# ---------------------------------------------------------------------------

class TestLegendData:
    def _extract_legend(self, graph: InfraGraph) -> list[dict]:
        html = _generate_and_read(graph)
        start = html.index("const LEGEND_ENTRIES = ") + len("const LEGEND_ENTRIES = ")
        end = html.index(";\n\n    // Build legend", start)
        return json.loads(html[start:end])

    def test_legend_includes_used_types_only(self) -> None:
        g = _make_simple_graph()
        legend = self._extract_legend(g)
        types_in_legend = {e["type"] for e in legend}
        assert "load_balancer" in types_in_legend
        assert "app_server" in types_in_legend
        assert "database" in types_in_legend

    def test_legend_excludes_unused_types(self) -> None:
        g = _make_simple_graph()
        legend = self._extract_legend(g)
        types_in_legend = {e["type"] for e in legend}
        assert "external_api" not in types_in_legend  # not in simple graph

    def test_legend_entries_have_color(self) -> None:
        g = _make_diverse_graph()
        legend = self._extract_legend(g)
        for entry in legend:
            assert "color" in entry
            assert entry["color"].startswith("#")


# ---------------------------------------------------------------------------
# UI feature presence tests
# ---------------------------------------------------------------------------

class TestUIFeatures:
    def test_search_box_present(self) -> None:
        g = _make_simple_graph()
        html = _generate_and_read(g)
        assert 'id="search"' in html

    def test_zoom_reset_button_present(self) -> None:
        g = _make_simple_graph()
        html = _generate_and_read(g)
        assert "Reset Zoom" in html or "reset" in html.lower()

    def test_tooltip_element_present(self) -> None:
        g = _make_simple_graph()
        html = _generate_and_read(g)
        assert 'id="tooltip"' in html

    def test_edge_legend_present(self) -> None:
        g = _make_simple_graph()
        html = _generate_and_read(g)
        assert "requires" in html
        assert "optional" in html
        assert "async" in html

    def test_d3_zoom_behavior(self) -> None:
        g = _make_simple_graph()
        html = _generate_and_read(g)
        assert "d3.zoom()" in html

    def test_component_and_edge_count_in_html(self) -> None:
        g = _make_simple_graph()
        html = _generate_and_read(g)
        assert "3 components" in html
        assert "2 edges" in html

    def test_empty_graph_generates_valid_html(self) -> None:
        g = InfraGraph()
        html = _generate_and_read(g)
        assert "<!DOCTYPE html>" in html
        assert "0 components" in html

    def test_force_simulation_present(self) -> None:
        g = _make_simple_graph()
        html = _generate_and_read(g)
        assert "forceSimulation" in html

    def test_drag_behavior_present(self) -> None:
        g = _make_simple_graph()
        html = _generate_and_read(g)
        assert "d3.drag()" in html

    def test_arrow_markers_for_direction(self) -> None:
        g = _make_simple_graph()
        html = _generate_and_read(g)
        assert "marker-end" in html
        # The template uses JS template literals: arrow-${d} and arrow-${d.type}
        assert "arrow-" in html
