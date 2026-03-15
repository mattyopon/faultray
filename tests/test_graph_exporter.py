"""Tests for Multi-Format Dependency Graph Exporter."""

from __future__ import annotations

import json

import pytest

from infrasim.model.components import (
    AutoScalingConfig,
    Component,
    ComponentType,
    Dependency,
    FailoverConfig,
    HealthStatus,
    ResourceMetrics,
)
from infrasim.model.graph import InfraGraph
from infrasim.reporter.graph_exporter import (
    DiagramFormat,
    DiagramOptions,
    GraphExporter,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_component(
    cid: str,
    ctype: ComponentType = ComponentType.APP_SERVER,
    port: int = 8080,
    replicas: int = 1,
    health: HealthStatus = HealthStatus.HEALTHY,
    autoscaling: AutoScalingConfig | None = None,
    failover: FailoverConfig | None = None,
    metrics: ResourceMetrics | None = None,
) -> Component:
    return Component(
        id=cid,
        name=cid.replace("_", " ").replace("-", " ").title(),
        type=ctype,
        port=port,
        replicas=replicas,
        health=health,
        autoscaling=autoscaling or AutoScalingConfig(),
        failover=failover or FailoverConfig(),
        metrics=metrics or ResourceMetrics(),
    )


def _simple_graph(
    components: list[Component],
    deps: list[tuple[str, str]] | None = None,
) -> InfraGraph:
    g = InfraGraph()
    for c in components:
        g.add_component(c)
    for src, tgt in deps or []:
        g.add_dependency(Dependency(source_id=src, target_id=tgt))
    return g


def _web_app_graph() -> InfraGraph:
    """Build a typical web app graph: LB -> app -> db."""
    lb = _make_component("nginx", ComponentType.LOAD_BALANCER, port=80, replicas=2)
    app = _make_component("app-server", ComponentType.APP_SERVER, port=8080, replicas=3)
    db = _make_component(
        "postgres", ComponentType.DATABASE, port=5432, replicas=1
    )  # SPOF

    return _simple_graph(
        [lb, app, db],
        [
            ("nginx", "app-server"),
            ("app-server", "postgres"),
        ],
    )


def _empty_graph() -> InfraGraph:
    return InfraGraph()


# ---------------------------------------------------------------------------
# GraphExporter.export dispatch
# ---------------------------------------------------------------------------


class TestGraphExporterDispatch:
    """Test that export() dispatches correctly to each format handler."""

    def test_export_all_formats(self):
        graph = _web_app_graph()
        exporter = GraphExporter()
        for fmt in DiagramFormat:
            result = exporter.export(graph, fmt)
            assert isinstance(result, str)
            assert len(result) > 0

    def test_export_invalid_format(self):
        graph = _web_app_graph()
        exporter = GraphExporter()
        with pytest.raises(ValueError, match="Unsupported diagram format"):
            exporter.export(graph, "invalid_format")  # type: ignore

    def test_export_with_custom_options(self):
        graph = _web_app_graph()
        exporter = GraphExporter()
        options = DiagramOptions(
            show_health=False,
            show_replicas=False,
            direction="LR",
            group_by_type=True,
        )
        result = exporter.export(graph, DiagramFormat.MERMAID, options)
        assert "LR" in result

    def test_export_empty_graph(self):
        graph = _empty_graph()
        exporter = GraphExporter()
        for fmt in DiagramFormat:
            result = exporter.export(graph, fmt)
            assert isinstance(result, str)


# ---------------------------------------------------------------------------
# Mermaid
# ---------------------------------------------------------------------------


class TestMermaidExport:
    def test_basic_output(self):
        graph = _web_app_graph()
        exporter = GraphExporter()
        result = exporter.to_mermaid(graph, DiagramOptions())
        assert "graph TB" in result
        assert "nginx" in result.lower() or "Nginx" in result
        assert "-->" in result

    def test_direction(self):
        graph = _web_app_graph()
        exporter = GraphExporter()
        result = exporter.to_mermaid(graph, DiagramOptions(direction="LR"))
        assert "graph LR" in result

    def test_group_by_type(self):
        graph = _web_app_graph()
        exporter = GraphExporter()
        result = exporter.to_mermaid(graph, DiagramOptions(group_by_type=True))
        assert "subgraph" in result

    def test_spof_highlighting(self):
        graph = _web_app_graph()
        exporter = GraphExporter()
        result = exporter.to_mermaid(graph, DiagramOptions(highlight_spof=True))
        assert "SPOF" in result
        assert "classDef spof" in result

    def test_spof_disabled(self):
        graph = _web_app_graph()
        exporter = GraphExporter()
        result = exporter.to_mermaid(graph, DiagramOptions(highlight_spof=False))
        assert "SPOF" not in result

    def test_health_class_definitions(self):
        graph = _web_app_graph()
        exporter = GraphExporter()
        result = exporter.to_mermaid(graph, DiagramOptions())
        assert "classDef healthy" in result or "classDef spof" in result

    def test_replicas_shown(self):
        graph = _web_app_graph()
        exporter = GraphExporter()
        result = exporter.to_mermaid(graph, DiagramOptions(show_replicas=True))
        assert "replicas:" in result

    def test_empty_graph(self):
        graph = _empty_graph()
        exporter = GraphExporter()
        result = exporter.to_mermaid(graph, DiagramOptions())
        assert "graph TB" in result


# ---------------------------------------------------------------------------
# D2
# ---------------------------------------------------------------------------


class TestD2Export:
    def test_basic_output(self):
        graph = _web_app_graph()
        exporter = GraphExporter()
        result = exporter.to_d2(graph, DiagramOptions())
        assert "direction:" in result
        assert "shape:" in result
        assert "style.fill:" in result
        assert "->" in result

    def test_direction_mapping(self):
        graph = _web_app_graph()
        exporter = GraphExporter()
        result = exporter.to_d2(graph, DiagramOptions(direction="LR"))
        assert "direction: right" in result

    def test_spof_marking(self):
        graph = _web_app_graph()
        exporter = GraphExporter()
        result = exporter.to_d2(graph, DiagramOptions(highlight_spof=True))
        assert "SPOF" in result

    def test_database_cylinder_shape(self):
        graph = _web_app_graph()
        exporter = GraphExporter()
        result = exporter.to_d2(graph, DiagramOptions())
        assert "cylinder" in result

    def test_group_by_type(self):
        graph = _web_app_graph()
        exporter = GraphExporter()
        result = exporter.to_d2(graph, DiagramOptions(group_by_type=True))
        # Should contain group blocks
        assert "{" in result

    def test_empty_graph(self):
        graph = _empty_graph()
        exporter = GraphExporter()
        result = exporter.to_d2(graph, DiagramOptions())
        assert "direction:" in result


# ---------------------------------------------------------------------------
# Graphviz DOT
# ---------------------------------------------------------------------------


class TestGraphvizExport:
    def test_basic_output(self):
        graph = _web_app_graph()
        exporter = GraphExporter()
        result = exporter.to_graphviz(graph, DiagramOptions())
        assert "digraph infrastructure" in result
        assert "rankdir=TB" in result
        assert "->" in result
        assert "fillcolor=" in result

    def test_direction(self):
        graph = _web_app_graph()
        exporter = GraphExporter()
        result = exporter.to_graphviz(graph, DiagramOptions(direction="LR"))
        assert "rankdir=LR" in result

    def test_spof_penwidth(self):
        graph = _web_app_graph()
        exporter = GraphExporter()
        result = exporter.to_graphviz(graph, DiagramOptions(highlight_spof=True))
        assert "penwidth=3" in result

    def test_group_by_type(self):
        graph = _web_app_graph()
        exporter = GraphExporter()
        result = exporter.to_graphviz(graph, DiagramOptions(group_by_type=True))
        assert "subgraph cluster_" in result

    def test_empty_graph(self):
        graph = _empty_graph()
        exporter = GraphExporter()
        result = exporter.to_graphviz(graph, DiagramOptions())
        assert "digraph infrastructure" in result
        assert "}" in result


# ---------------------------------------------------------------------------
# PlantUML
# ---------------------------------------------------------------------------


class TestPlantUMLExport:
    def test_basic_output(self):
        graph = _web_app_graph()
        exporter = GraphExporter()
        result = exporter.to_plantuml(graph, DiagramOptions())
        assert "@startuml" in result
        assert "@enduml" in result
        assert "-->" in result
        assert "!define HEALTHY" in result

    def test_database_type(self):
        graph = _web_app_graph()
        exporter = GraphExporter()
        result = exporter.to_plantuml(graph, DiagramOptions())
        assert 'database "' in result

    def test_spof_marking(self):
        graph = _web_app_graph()
        exporter = GraphExporter()
        result = exporter.to_plantuml(graph, DiagramOptions(highlight_spof=True))
        assert "SPOF" in result

    def test_replicas_in_label(self):
        graph = _web_app_graph()
        exporter = GraphExporter()
        result = exporter.to_plantuml(graph, DiagramOptions(show_replicas=True))
        assert "(x3)" in result  # app-server has 3 replicas

    def test_empty_graph(self):
        graph = _empty_graph()
        exporter = GraphExporter()
        result = exporter.to_plantuml(graph, DiagramOptions())
        assert "@startuml" in result
        assert "@enduml" in result


# ---------------------------------------------------------------------------
# ASCII Art
# ---------------------------------------------------------------------------


class TestASCIIExport:
    def test_basic_output(self):
        graph = _web_app_graph()
        exporter = GraphExporter()
        result = exporter.to_ascii(graph, DiagramOptions())
        assert "\u250c" in result  # box drawing top-left
        assert "\u2514" in result  # box drawing bottom-left
        assert "\u25bc" in result  # down arrow

    def test_contains_component_names(self):
        graph = _web_app_graph()
        exporter = GraphExporter()
        result = exporter.to_ascii(graph, DiagramOptions())
        # The names are title-cased from the id
        assert "Nginx" in result or "nginx" in result.lower()

    def test_spof_marking(self):
        graph = _web_app_graph()
        exporter = GraphExporter()
        result = exporter.to_ascii(graph, DiagramOptions(highlight_spof=True))
        assert "SPOF" in result

    def test_empty_graph(self):
        graph = _empty_graph()
        exporter = GraphExporter()
        result = exporter.to_ascii(graph, DiagramOptions())
        assert "empty graph" in result

    def test_replicas_shown(self):
        graph = _web_app_graph()
        exporter = GraphExporter()
        result = exporter.to_ascii(graph, DiagramOptions(show_replicas=True))
        assert "replicas:" in result


# ---------------------------------------------------------------------------
# JSON
# ---------------------------------------------------------------------------


class TestJSONExport:
    def test_basic_output(self):
        graph = _web_app_graph()
        exporter = GraphExporter()
        result = exporter.to_json(graph, DiagramOptions())
        data = json.loads(result)
        assert data["format"] == "faultzero-dependency-graph"
        assert "nodes" in data
        assert "edges" in data
        assert "summary" in data

    def test_node_count(self):
        graph = _web_app_graph()
        exporter = GraphExporter()
        result = exporter.to_json(graph, DiagramOptions())
        data = json.loads(result)
        assert len(data["nodes"]) == 3

    def test_edge_count(self):
        graph = _web_app_graph()
        exporter = GraphExporter()
        result = exporter.to_json(graph, DiagramOptions())
        data = json.loads(result)
        assert len(data["edges"]) == 2

    def test_spof_flag(self):
        graph = _web_app_graph()
        exporter = GraphExporter()
        result = exporter.to_json(graph, DiagramOptions(highlight_spof=True))
        data = json.loads(result)
        spof_nodes = [n for n in data["nodes"] if n.get("is_spof")]
        assert len(spof_nodes) >= 1  # postgres is SPOF

    def test_health_included(self):
        graph = _web_app_graph()
        exporter = GraphExporter()
        result = exporter.to_json(graph, DiagramOptions(show_health=True))
        data = json.loads(result)
        for node in data["nodes"]:
            assert "health" in node

    def test_utilization_optional(self):
        graph = _web_app_graph()
        exporter = GraphExporter()

        # Without utilization
        result = exporter.to_json(graph, DiagramOptions(show_utilization=False))
        data = json.loads(result)
        for node in data["nodes"]:
            assert "utilization" not in node

        # With utilization
        result = exporter.to_json(graph, DiagramOptions(show_utilization=True))
        data = json.loads(result)
        for node in data["nodes"]:
            assert "utilization" in node

    def test_risk_level_optional(self):
        graph = _web_app_graph()
        exporter = GraphExporter()

        result = exporter.to_json(
            graph, DiagramOptions(show_risk_level=True, highlight_spof=True)
        )
        data = json.loads(result)
        risk_levels = {n["risk_level"] for n in data["nodes"]}
        assert "critical" in risk_levels or "normal" in risk_levels

    def test_empty_graph(self):
        graph = _empty_graph()
        exporter = GraphExporter()
        result = exporter.to_json(graph, DiagramOptions())
        data = json.loads(result)
        assert len(data["nodes"]) == 0
        assert len(data["edges"]) == 0

    def test_valid_json(self):
        graph = _web_app_graph()
        exporter = GraphExporter()
        result = exporter.to_json(graph, DiagramOptions())
        # Should not raise
        parsed = json.loads(result)
        assert isinstance(parsed, dict)


# ---------------------------------------------------------------------------
# Degraded / Down health status
# ---------------------------------------------------------------------------


class TestHealthStatusVariations:
    def test_degraded_component(self):
        graph = _simple_graph(
            [
                _make_component("svc", health=HealthStatus.DEGRADED, replicas=2),
                _make_component("db", ComponentType.DATABASE, health=HealthStatus.HEALTHY),
            ],
            [("svc", "db")],
        )
        exporter = GraphExporter()
        mermaid = exporter.to_mermaid(graph, DiagramOptions())
        assert "degraded" in mermaid

    def test_down_component(self):
        graph = _simple_graph(
            [
                _make_component("svc", health=HealthStatus.DOWN, replicas=2),
                _make_component("db", ComponentType.DATABASE, health=HealthStatus.HEALTHY),
            ],
            [("svc", "db")],
        )
        exporter = GraphExporter()
        mermaid = exporter.to_mermaid(graph, DiagramOptions())
        assert "down" in mermaid

    def test_overloaded_component(self):
        graph = _simple_graph(
            [
                _make_component("svc", health=HealthStatus.OVERLOADED, replicas=2),
                _make_component("db", ComponentType.DATABASE, health=HealthStatus.HEALTHY),
            ],
            [("svc", "db")],
        )
        exporter = GraphExporter()
        json_out = exporter.to_json(graph, DiagramOptions(show_health=True))
        data = json.loads(json_out)
        healths = {n["health"] for n in data["nodes"]}
        assert "overloaded" in healths


# ---------------------------------------------------------------------------
# Complex graph
# ---------------------------------------------------------------------------


class TestComplexGraph:
    def test_multi_dependency_graph(self):
        """Test a graph with multiple dependency types."""
        lb = _make_component("lb", ComponentType.LOAD_BALANCER, replicas=2)
        web = _make_component("web", ComponentType.WEB_SERVER, replicas=3)
        api = _make_component("api", ComponentType.APP_SERVER, replicas=3)
        db = _make_component("db", ComponentType.DATABASE, replicas=2)
        cache = _make_component("redis", ComponentType.CACHE, replicas=2)
        queue = _make_component("mq", ComponentType.QUEUE, replicas=1)

        graph = _simple_graph(
            [lb, web, api, db, cache, queue],
            [
                ("lb", "web"),
                ("web", "api"),
                ("api", "db"),
                ("api", "redis"),
                ("api", "mq"),
            ],
        )

        exporter = GraphExporter()
        for fmt in DiagramFormat:
            result = exporter.export(graph, fmt)
            assert len(result) > 0

    def test_single_component_no_edges(self):
        """Test a graph with a single component and no edges."""
        graph = _simple_graph([_make_component("standalone")])
        exporter = GraphExporter()
        for fmt in DiagramFormat:
            result = exporter.export(graph, fmt)
            assert len(result) > 0
