"""Multi-Format Dependency Graph Exporter.

Export infrastructure dependency graphs in multiple diagram formats:
- Mermaid.js (for GitHub, GitLab, Notion, Confluence)
- D2 (modern diagram language)
- Graphviz DOT (for graphviz tools)
- PlantUML (for documentation)
- ASCII art (for terminals and plain text)
- JSON (for custom tools)

Each format includes component metadata, health status coloring,
and dependency relationships.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from infrasim.model.components import Component, ComponentType, HealthStatus
from infrasim.model.graph import InfraGraph


class DiagramFormat(str, Enum):
    """Supported diagram output formats."""

    MERMAID = "mermaid"
    D2 = "d2"
    GRAPHVIZ = "graphviz"
    PLANTUML = "plantuml"
    ASCII = "ascii"
    JSON = "json"


@dataclass
class DiagramOptions:
    """Options controlling diagram content and appearance."""

    show_health: bool = True
    show_replicas: bool = True
    show_utilization: bool = False
    show_risk_level: bool = False
    direction: str = "TB"  # TB, LR, BT, RL
    group_by_type: bool = False
    highlight_spof: bool = True
    dark_theme: bool = False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TYPE_LABELS: dict[ComponentType, str] = {
    ComponentType.LOAD_BALANCER: "Load Balancers",
    ComponentType.WEB_SERVER: "Web Servers",
    ComponentType.APP_SERVER: "Application Servers",
    ComponentType.DATABASE: "Databases",
    ComponentType.CACHE: "Caches",
    ComponentType.QUEUE: "Message Queues",
    ComponentType.STORAGE: "Storage",
    ComponentType.DNS: "DNS",
    ComponentType.EXTERNAL_API: "External APIs",
    ComponentType.CUSTOM: "Custom",
}

_HEALTH_ICONS: dict[HealthStatus, str] = {
    HealthStatus.HEALTHY: "\U0001f7e2",
    HealthStatus.DEGRADED: "\U0001f7e1",
    HealthStatus.OVERLOADED: "\U0001f7e0",
    HealthStatus.DOWN: "\U0001f534",
}

# Colour palettes
_HEALTH_COLORS: dict[HealthStatus, str] = {
    HealthStatus.HEALTHY: "#28a745",
    HealthStatus.DEGRADED: "#ffc107",
    HealthStatus.OVERLOADED: "#fd7e14",
    HealthStatus.DOWN: "#dc3545",
}

_SPOF_COLOR = "#dc3545"

# Shape mapping for D2
_D2_SHAPES: dict[ComponentType, str] = {
    ComponentType.LOAD_BALANCER: "hexagon",
    ComponentType.WEB_SERVER: "rectangle",
    ComponentType.APP_SERVER: "rectangle",
    ComponentType.DATABASE: "cylinder",
    ComponentType.CACHE: "diamond",
    ComponentType.QUEUE: "queue",
    ComponentType.STORAGE: "stored_data",
    ComponentType.DNS: "cloud",
    ComponentType.EXTERNAL_API: "cloud",
    ComponentType.CUSTOM: "rectangle",
}


def _is_spof(comp: Component, graph: InfraGraph) -> bool:
    """Return True if the component is a single point of failure."""
    dependents = graph.get_dependents(comp.id)
    return comp.replicas <= 1 and len(dependents) > 0


def _sanitize_mermaid_id(cid: str) -> str:
    """Make a component ID safe for Mermaid node identifiers."""
    return cid.replace("-", "_").replace(".", "_").replace(" ", "_")


def _sanitize_d2_id(cid: str) -> str:
    """Make a component ID safe for D2 identifiers."""
    return cid.replace("-", "_").replace(".", "_").replace(" ", "_")


def _node_label(comp: Component, options: DiagramOptions, graph: InfraGraph) -> str:
    """Build a human-readable label for a component node."""
    parts = [comp.name or comp.id]
    if options.show_replicas:
        parts.append(f"replicas: {comp.replicas}")
    if options.show_utilization:
        util = comp.utilization()
        parts.append(f"util: {util:.0f}%")
    if options.show_health:
        icon = _HEALTH_ICONS.get(comp.health, "")
        if options.highlight_spof and _is_spof(comp, graph):
            parts.append(f"\u26a0\ufe0f SPOF")
        else:
            parts.append(f"{icon} {comp.health.value}")
    return parts


# ---------------------------------------------------------------------------
# GraphExporter
# ---------------------------------------------------------------------------


class GraphExporter:
    """Export an InfraGraph in various diagram formats."""

    def export(
        self,
        graph: InfraGraph,
        fmt: DiagramFormat,
        options: DiagramOptions | None = None,
    ) -> str:
        """Dispatch to the appropriate format exporter."""
        if options is None:
            options = DiagramOptions()

        dispatch = {
            DiagramFormat.MERMAID: self.to_mermaid,
            DiagramFormat.D2: self.to_d2,
            DiagramFormat.GRAPHVIZ: self.to_graphviz,
            DiagramFormat.PLANTUML: self.to_plantuml,
            DiagramFormat.ASCII: self.to_ascii,
            DiagramFormat.JSON: self.to_json,
        }
        handler = dispatch.get(fmt)
        if handler is None:
            raise ValueError(f"Unsupported diagram format: {fmt}")
        return handler(graph, options)

    # ------------------------------------------------------------------
    # Mermaid
    # ------------------------------------------------------------------

    def to_mermaid(self, graph: InfraGraph, options: DiagramOptions) -> str:
        lines: list[str] = [f"graph {options.direction}"]

        components = list(graph.components.values())
        if not components:
            return "graph TB\n"

        # Collect health classes used
        used_classes: set[str] = set()
        spof_used = False

        if options.group_by_type:
            groups: dict[ComponentType, list[Component]] = {}
            for comp in components:
                groups.setdefault(comp.type, []).append(comp)

            for ctype, group_comps in groups.items():
                label = _TYPE_LABELS.get(ctype, ctype.value)
                sg_id = ctype.value.replace("_", "")
                lines.append(f'    subgraph {sg_id}["{label}"]')
                for comp in group_comps:
                    lines.extend(
                        self._mermaid_node(comp, options, graph, used_classes, indent=8)
                    )
                    if options.highlight_spof and _is_spof(comp, graph):
                        spof_used = True
                lines.append("    end")
        else:
            for comp in components:
                lines.extend(
                    self._mermaid_node(comp, options, graph, used_classes, indent=4)
                )
                if options.highlight_spof and _is_spof(comp, graph):
                    spof_used = True

        # Edges
        for u, v, data in graph._graph.edges(data=True):
            sid = _sanitize_mermaid_id(u)
            tid = _sanitize_mermaid_id(v)
            lines.append(f"    {sid} --> {tid}")

        # Class definitions
        for cls_name in sorted(used_classes):
            if cls_name == "spof":
                lines.append(
                    f"    classDef spof fill:{_SPOF_COLOR},color:#fff,"
                    "stroke:#ff0,stroke-width:3px"
                )
            else:
                # cls_name should match a HealthStatus value
                try:
                    hs = HealthStatus(cls_name)
                    color = _HEALTH_COLORS[hs]
                    lines.append(f"    classDef {cls_name} fill:{color},color:#fff")
                except ValueError:
                    pass

        return "\n".join(lines) + "\n"

    def _mermaid_node(
        self,
        comp: Component,
        options: DiagramOptions,
        graph: InfraGraph,
        used_classes: set[str],
        indent: int = 4,
    ) -> list[str]:
        pad = " " * indent
        sid = _sanitize_mermaid_id(comp.id)
        parts = _node_label(comp, options, graph)
        label = "<br/>".join(parts)
        is_spof = options.highlight_spof and _is_spof(comp, graph)

        if is_spof:
            cls = "spof"
        else:
            cls = comp.health.value
        used_classes.add(cls)

        return [f'{pad}{sid}["{label}"]:::{cls}']

    # ------------------------------------------------------------------
    # D2
    # ------------------------------------------------------------------

    def to_d2(self, graph: InfraGraph, options: DiagramOptions) -> str:
        lines: list[str] = []

        direction_map = {"TB": "down", "LR": "right", "BT": "up", "RL": "left"}
        d2_dir = direction_map.get(options.direction, "down")
        lines.append(f"direction: {d2_dir}")
        lines.append("")

        components = list(graph.components.values())
        if not components:
            return "direction: down\n"

        if options.group_by_type:
            groups: dict[ComponentType, list[Component]] = {}
            for comp in components:
                groups.setdefault(comp.type, []).append(comp)

            for ctype, group_comps in groups.items():
                group_label = _TYPE_LABELS.get(ctype, ctype.value)
                group_id = _sanitize_d2_id(ctype.value)
                lines.append(f"{group_id}: {group_label} {{")
                for comp in group_comps:
                    lines.extend(self._d2_node(comp, options, graph, indent=2))
                lines.append("}")
                lines.append("")
        else:
            for comp in components:
                lines.extend(self._d2_node(comp, options, graph, indent=0))
                lines.append("")

        # Edges
        for u, v, data in graph._graph.edges(data=True):
            sid = _sanitize_d2_id(u)
            tid = _sanitize_d2_id(v)
            dep = data.get("dependency")
            edge_label = dep.dependency_type if dep else "depends_on"

            if options.group_by_type:
                src_comp = graph.get_component(u)
                tgt_comp = graph.get_component(v)
                if src_comp and tgt_comp:
                    src_group = _sanitize_d2_id(src_comp.type.value)
                    tgt_group = _sanitize_d2_id(tgt_comp.type.value)
                    lines.append(
                        f"{src_group}.{sid} -> {tgt_group}.{tid}: {edge_label}"
                    )
                else:
                    lines.append(f"{sid} -> {tid}: {edge_label}")
            else:
                lines.append(f"{sid} -> {tid}: {edge_label}")

        return "\n".join(lines) + "\n"

    def _d2_node(
        self,
        comp: Component,
        options: DiagramOptions,
        graph: InfraGraph,
        indent: int = 0,
    ) -> list[str]:
        pad = " " * indent
        sid = _sanitize_d2_id(comp.id)
        is_spof = options.highlight_spof and _is_spof(comp, graph)

        label_parts = [comp.name or comp.id]
        if options.show_replicas and comp.replicas > 1:
            label_parts[0] += f" (x{comp.replicas})"
        if is_spof:
            label_parts[0] += " \u26a0\ufe0f SPOF"

        shape = _D2_SHAPES.get(comp.type, "rectangle")
        color = _SPOF_COLOR if is_spof else _HEALTH_COLORS.get(comp.health, "#28a745")

        lines = [
            f"{pad}{sid}: {label_parts[0]} {{",
            f"{pad}  shape: {shape}",
            f'{pad}  style.fill: "{color}"',
            f"{pad}}}",
        ]
        return lines

    # ------------------------------------------------------------------
    # Graphviz DOT
    # ------------------------------------------------------------------

    def to_graphviz(self, graph: InfraGraph, options: DiagramOptions) -> str:
        lines: list[str] = [
            "digraph infrastructure {",
            f"  rankdir={options.direction};",
            "  node [shape=box, style=filled];",
        ]

        components = list(graph.components.values())
        if not components:
            lines.append("}")
            return "\n".join(lines) + "\n"

        if options.group_by_type:
            groups: dict[ComponentType, list[Component]] = {}
            for comp in components:
                groups.setdefault(comp.type, []).append(comp)

            for idx, (ctype, group_comps) in enumerate(groups.items()):
                label = _TYPE_LABELS.get(ctype, ctype.value)
                lines.append(f'  subgraph cluster_{idx} {{')
                lines.append(f'    label="{label}";')
                for comp in group_comps:
                    lines.append(self._graphviz_node(comp, options, graph, indent=4))
                lines.append("  }")
        else:
            for comp in components:
                lines.append(self._graphviz_node(comp, options, graph, indent=2))

        # Edges
        for u, v, _data in graph._graph.edges(data=True):
            lines.append(f"  {_sanitize_mermaid_id(u)} -> {_sanitize_mermaid_id(v)};")

        lines.append("}")
        return "\n".join(lines) + "\n"

    def _graphviz_node(
        self,
        comp: Component,
        options: DiagramOptions,
        graph: InfraGraph,
        indent: int = 2,
    ) -> str:
        pad = " " * indent
        sid = _sanitize_mermaid_id(comp.id)
        is_spof = options.highlight_spof and _is_spof(comp, graph)

        label_parts = [comp.name or comp.id]
        if options.show_replicas:
            label_parts.append(f"replicas: {comp.replicas}")
        if options.show_utilization:
            util = comp.utilization()
            label_parts.append(f"util: {util:.0f}%")
        if options.show_health and is_spof:
            label_parts.append("\u26a0 SPOF")
        elif options.show_health:
            label_parts.append(comp.health.value)

        label = "\\n".join(label_parts)
        color = _SPOF_COLOR if is_spof else _HEALTH_COLORS.get(comp.health, "#28a745")

        attrs = [f'label="{label}"', f'fillcolor="{color}"', 'fontcolor="white"']
        if is_spof:
            attrs.append("penwidth=3")

        # Use cylinder shape for databases
        shape_map: dict[ComponentType, str] = {
            ComponentType.DATABASE: "cylinder",
            ComponentType.LOAD_BALANCER: "hexagon",
            ComponentType.QUEUE: "parallelogram",
            ComponentType.STORAGE: "folder",
            ComponentType.DNS: "ellipse",
            ComponentType.EXTERNAL_API: "ellipse",
        }
        node_shape = shape_map.get(comp.type)
        if node_shape:
            attrs.append(f"shape={node_shape}")

        return f"{pad}{sid} [{', '.join(attrs)}];"

    # ------------------------------------------------------------------
    # PlantUML
    # ------------------------------------------------------------------

    def to_plantuml(self, graph: InfraGraph, options: DiagramOptions) -> str:
        lines: list[str] = ["@startuml"]
        lines.append("!define HEALTHY #28a745")
        lines.append("!define DEGRADED #ffc107")
        lines.append("!define OVERLOADED #fd7e14")
        lines.append("!define DOWN #dc3545")
        lines.append("!define SPOF #dc3545")
        lines.append("")

        components = list(graph.components.values())

        # PlantUML type mapping
        puml_types: dict[ComponentType, str] = {
            ComponentType.LOAD_BALANCER: "component",
            ComponentType.WEB_SERVER: "component",
            ComponentType.APP_SERVER: "component",
            ComponentType.DATABASE: "database",
            ComponentType.CACHE: "component",
            ComponentType.QUEUE: "queue",
            ComponentType.STORAGE: "storage",
            ComponentType.DNS: "cloud",
            ComponentType.EXTERNAL_API: "cloud",
            ComponentType.CUSTOM: "component",
        }

        for comp in components:
            sid = _sanitize_mermaid_id(comp.id)
            is_spof = options.highlight_spof and _is_spof(comp, graph)
            puml_type = puml_types.get(comp.type, "component")

            label = comp.name or comp.id
            if options.show_replicas and comp.replicas > 1:
                label += f" (x{comp.replicas})"
            if is_spof:
                label += " \u26a0 SPOF"

            if is_spof:
                color = "SPOF"
            else:
                color_map = {
                    HealthStatus.HEALTHY: "HEALTHY",
                    HealthStatus.DEGRADED: "DEGRADED",
                    HealthStatus.OVERLOADED: "OVERLOADED",
                    HealthStatus.DOWN: "DOWN",
                }
                color = color_map.get(comp.health, "HEALTHY")

            lines.append(f'{puml_type} "{label}" as {sid} {color}')

        lines.append("")

        # Edges
        for u, v, _data in graph._graph.edges(data=True):
            sid = _sanitize_mermaid_id(u)
            tid = _sanitize_mermaid_id(v)
            lines.append(f"{sid} --> {tid}")

        lines.append("")
        lines.append("@enduml")
        return "\n".join(lines) + "\n"

    # ------------------------------------------------------------------
    # ASCII Art
    # ------------------------------------------------------------------

    def to_ascii(self, graph: InfraGraph, options: DiagramOptions) -> str:
        components = list(graph.components.values())
        if not components:
            return "(empty graph)\n"

        # Build a topological ordering for display
        try:
            import networkx as nx

            ordered_ids = list(nx.topological_sort(graph._graph))
        except Exception:
            ordered_ids = [c.id for c in components]

        lines: list[str] = []

        for idx, cid in enumerate(ordered_ids):
            comp = graph.get_component(cid)
            if comp is None:
                continue

            is_spof = options.highlight_spof and _is_spof(comp, graph)

            content_lines = [comp.name or comp.id]
            if options.show_replicas:
                content_lines.append(f"replicas: {comp.replicas}")
            if options.show_utilization:
                util = comp.utilization()
                content_lines.append(f"util: {util:.0f}%")
            if options.show_health:
                if is_spof:
                    content_lines.append("\u26a0\ufe0f SPOF")
                else:
                    icon = _HEALTH_ICONS.get(comp.health, "")
                    content_lines.append(f"{icon} {comp.health.value}")

            # Determine box width
            max_len = max(len(line) for line in content_lines)
            box_width = max_len + 4  # 2 padding + 2 border chars

            # Draw box
            top = "\u250c" + "\u2500" * box_width + "\u2510"
            bottom = "\u2514" + "\u2500" * box_width + "\u2518"
            lines.append(top)
            for cl in content_lines:
                padded = cl.center(box_width)
                lines.append(f"\u2502{padded}\u2502")
            lines.append(bottom)

            # Draw arrow to next component if there are successors
            if idx < len(ordered_ids) - 1:
                arrow_pad = " " * (box_width // 2)
                lines.append(f"{arrow_pad}  \u2502")
                lines.append(f"{arrow_pad}  \u25bc")

        return "\n".join(lines) + "\n"

    # ------------------------------------------------------------------
    # JSON
    # ------------------------------------------------------------------

    def to_json(self, graph: InfraGraph, options: DiagramOptions) -> str:
        components_data: list[dict[str, Any]] = []
        for comp in graph.components.values():
            is_spof = options.highlight_spof and _is_spof(comp, graph)
            node: dict[str, Any] = {
                "id": comp.id,
                "name": comp.name,
                "type": comp.type.value,
            }
            if options.show_replicas:
                node["replicas"] = comp.replicas
            if options.show_health:
                node["health"] = comp.health.value
            if options.show_utilization:
                node["utilization"] = round(comp.utilization(), 1)
            if options.highlight_spof:
                node["is_spof"] = is_spof
            if options.show_risk_level:
                node["risk_level"] = "critical" if is_spof else "normal"
            components_data.append(node)

        edges_data: list[dict[str, Any]] = []
        for u, v, data in graph._graph.edges(data=True):
            dep = data.get("dependency")
            edge: dict[str, Any] = {
                "source": u,
                "target": v,
            }
            if dep:
                edge["dependency_type"] = dep.dependency_type
                edge["protocol"] = dep.protocol
            edges_data.append(edge)

        output = {
            "format": "faultzero-dependency-graph",
            "version": "1.0",
            "options": {
                "direction": options.direction,
                "group_by_type": options.group_by_type,
                "highlight_spof": options.highlight_spof,
            },
            "nodes": components_data,
            "edges": edges_data,
            "summary": graph.summary(),
        }

        return json.dumps(output, indent=2, default=str) + "\n"
