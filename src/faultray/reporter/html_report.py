# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""HTML report generator - produces standalone HTML simulation reports."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from xml.sax.saxutils import escape

from jinja2 import Environment, FileSystemLoader

from faultray.model.components import HealthStatus
from faultray.model.graph import InfraGraph
from faultray.simulator.engine import ScenarioResult, SimulationReport


# ---------------------------------------------------------------------------
# Template helpers
# ---------------------------------------------------------------------------

_TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"


def _health_icon(health: HealthStatus) -> str:
    return {
        HealthStatus.HEALTHY: "OK",
        HealthStatus.DEGRADED: "WARN",
        HealthStatus.OVERLOADED: "OVER",
        HealthStatus.DOWN: "DOWN",
    }.get(health, "?")


def _health_class(health: HealthStatus) -> str:
    return {
        HealthStatus.HEALTHY: "healthy",
        HealthStatus.DEGRADED: "degraded",
        HealthStatus.OVERLOADED: "overloaded",
        HealthStatus.DOWN: "down",
    }.get(health, "healthy")


def _score_color(score: float) -> str:
    if score >= 80:
        return "green"
    if score >= 60:
        return "yellow"
    return "red"


def _util_color(util: float) -> str:
    if util > 80:
        return "red"
    if util > 60:
        return "yellow"
    return "green"


# ---------------------------------------------------------------------------
# Finding / cascade data helpers
# ---------------------------------------------------------------------------

def _build_finding(result: ScenarioResult) -> dict:
    """Convert a ScenarioResult (or DynamicScenarioResult) into a template-friendly dict."""
    effects = []
    prev_time = 0

    # DynamicScenarioResult has snapshots with cascade_effects instead of cascade
    if hasattr(result, "cascade"):
        raw_effects = result.cascade.effects
    elif hasattr(result, "snapshots"):
        raw_effects = [
            eff
            for snap in result.snapshots
            for eff in snap.cascade_effects
        ]
    else:
        raw_effects = []

    for eff in raw_effects:
        time_str = ""
        if eff.estimated_time_seconds > 0:
            delta = eff.estimated_time_seconds - prev_time
            time_str = f"+{delta}s"
            prev_time = eff.estimated_time_seconds

        effects.append({
            "component_name": eff.component_name,
            "health_icon": _health_icon(eff.health),
            "health_class": _health_class(eff.health),
            "reason": eff.reason,
            "time_str": time_str,
        })

    # DynamicScenarioResult uses peak_severity instead of risk_score
    risk = getattr(result, "risk_score", None)
    if risk is None:
        risk = getattr(result, "peak_severity", 0.0)

    return {
        "name": result.scenario.name,
        "description": result.scenario.description,
        "risk_score": f"{risk:.1f}",
        "effects": effects,
    }


# ---------------------------------------------------------------------------
# SVG dependency map
# ---------------------------------------------------------------------------

def _build_dependency_svg(graph: InfraGraph) -> str:
    """Build a simple SVG diagram of the dependency graph.

    Nodes are laid out in layers by type:
      load_balancer / web_server  -> app_server -> database / cache / queue / storage / dns / external_api / custom
    """
    # Categorize components into layers
    layer_order = {
        "load_balancer": 0,
        "web_server": 0,
        "dns": 0,
        "app_server": 1,
        "external_api": 1,
        "custom": 1,
        "database": 2,
        "cache": 2,
        "queue": 2,
        "storage": 2,
    }

    layers: dict[int, list[str]] = {}
    for comp in graph.components.values():
        layer = layer_order.get(comp.type.value, 1)
        layers.setdefault(layer, []).append(comp.id)

    if not layers:
        return '<svg width="200" height="40"><text x="10" y="25" fill="#8b949e">No components</text></svg>'

    # Layout constants
    node_w = 160
    node_h = 40
    h_gap = 40
    v_gap = 80
    padding = 30

    # Calculate positions
    positions: dict[str, tuple[int, int]] = {}
    max_layer_width = 0
    sorted_layers = sorted(layers.keys())

    for layer_idx in sorted_layers:
        ids = layers[layer_idx]
        layer_width = len(ids) * node_w + (len(ids) - 1) * h_gap
        max_layer_width = max(max_layer_width, layer_width)

    svg_w = max(max_layer_width + padding * 2, 300)

    for layer_idx in sorted_layers:
        ids = layers[layer_idx]
        layer_width = len(ids) * node_w + (len(ids) - 1) * h_gap
        start_x = (svg_w - layer_width) / 2
        y = padding + layer_idx * (node_h + v_gap)
        for i, comp_id in enumerate(ids):
            x = start_x + i * (node_w + h_gap)
            positions[comp_id] = (int(x), int(y))

    svg_h = padding * 2 + (max(sorted_layers) + 1) * (node_h + v_gap)

    # Build SVG
    parts: list[str] = []
    parts.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{svg_w}" height="{svg_h}" '
        f'viewBox="0 0 {svg_w} {svg_h}">'
    )

    # Arrowhead marker
    parts.append(
        '<defs>'
        '<marker id="arrowhead" markerWidth="10" markerHeight="7" refX="10" refY="3.5" orient="auto">'
        '<polygon points="0 0, 10 3.5, 0 7" fill="#58a6ff"/>'
        '</marker>'
        '</defs>'
    )

    # Edges
    graph_dict = graph.to_dict()
    for dep in graph_dict.get("dependencies", []):
        src = dep.get("source_id", "")
        tgt = dep.get("target_id", "")
        if src in positions and tgt in positions:
            sx, sy = positions[src]
            tx, ty = positions[tgt]
            # Draw from bottom center of source to top center of target
            x1 = sx + node_w / 2
            y1 = sy + node_h
            x2 = tx + node_w / 2
            y2 = ty
            parts.append(
                f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" '
                f'stroke="#58a6ff" stroke-width="1.5" marker-end="url(#arrowhead)" '
                f'opacity="0.7"/>'
            )

    # Nodes
    type_colors = {
        "load_balancer": "#bc8cff",
        "web_server": "#bc8cff",
        "app_server": "#58a6ff",
        "database": "#3fb950",
        "cache": "#d29922",
        "queue": "#d29922",
        "storage": "#3fb950",
        "dns": "#8b949e",
        "external_api": "#8b949e",
        "custom": "#8b949e",
    }

    for comp in graph.components.values():
        if comp.id not in positions:
            continue
        x, y = positions[comp.id]
        color = type_colors.get(comp.type.value, "#8b949e")

        parts.append(
            f'<rect x="{x}" y="{y}" width="{node_w}" height="{node_h}" '
            f'rx="6" ry="6" fill="#161b22" stroke="{color}" stroke-width="1.5"/>'
        )

        # Truncate long names
        label = comp.name if len(comp.name) <= 20 else comp.name[:18] + ".."
        label = escape(label)  # Sanitize for XML/SVG
        text_x = x + node_w / 2
        text_y = y + node_h / 2 + 5
        parts.append(
            f'<text x="{text_x}" y="{text_y}" fill="{color}" font-size="12" '
            f'font-family="sans-serif" text-anchor="middle">{label}</text>'
        )

    parts.append("</svg>")
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_html_report(report: SimulationReport | list, graph: InfraGraph) -> str:
    """Render a standalone HTML report string.

    Args:
        report: The simulation report produced by :class:`SimulationEngine`,
                or a plain list of :class:`ScenarioResult` (from dynamic simulation).
        graph: The infrastructure graph that was simulated.

    Returns:
        A complete HTML document as a string.
    """
    # Handle plain list input (e.g. from dynamic simulation)
    if isinstance(report, list):
        report = SimulationReport(results=report)

    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATE_DIR)),
        autoescape=True,
    )
    template = env.get_template("report.html")

    score = report.resilience_score

    # Prepare component rows
    comp_rows = []
    for comp in graph.components.values():
        util = comp.utilization()
        comp_rows.append({
            "name": comp.name,
            "type": comp.type.value,
            "host": comp.host,
            "port": comp.port,
            "replicas": comp.replicas,
            "utilization": f"{util:.0f}",
            "util_color": _util_color(util),
            "util_width": min(util, 100),
            "cpu": f"{comp.metrics.cpu_percent:.0f}",
            "memory": f"{comp.metrics.memory_percent:.0f}",
            "disk": f"{comp.metrics.disk_percent:.0f}",
            "connections": comp.metrics.network_connections,
        })

    # Build score explanation text
    score_explanation_lines = [
        "The resilience score measures structural health: single points of failure "
        "(SPOFs), resource utilization headroom, and dependency chain depth.",
    ]
    if score < 70 and not report.critical_findings and not report.warnings:
        score_explanation_lines.append(
            "All scenarios passed, indicating good runtime resilience despite "
            "architectural gaps reflected in the score."
        )
    elif report.critical_findings:
        score_explanation_lines.append(
            f"{len(report.critical_findings)} critical scenario(s) detected "
            "cascade failures that could cause widespread outages."
        )

    context = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "resilience_score": f"{score:.0f}",
        "score_color": _score_color(score),
        "total_components": len(graph.components),
        "critical_count": len(report.critical_findings),
        "warning_count": len(report.warnings),
        "passed_count": len(report.passed),
        "critical_findings": [_build_finding(r) for r in report.critical_findings],
        "warning_findings": [_build_finding(r) for r in report.warnings],
        "components": comp_rows,
        "dependency_svg": _build_dependency_svg(graph),
        "score_explanation": score_explanation_lines,
    }

    return template.render(**context)


def save_html_report(report: SimulationReport | list, graph: InfraGraph, output_path: Path) -> None:
    """Generate and write an HTML report to disk.

    Args:
        report: The simulation report, or a plain list of ScenarioResult.
        graph: The infrastructure graph.
        output_path: File path for the HTML output.
    """
    html = generate_html_report(report, graph)
    output_path.write_text(html, encoding="utf-8")
