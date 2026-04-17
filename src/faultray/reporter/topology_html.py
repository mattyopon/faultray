# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""Interactive HTML Topology Map Generator.

Produces a standalone HTML file with a D3.js force-directed graph
that can be opened in any browser. Supports zoom/pan, hover tooltips,
component search, and a color legend.
"""

from __future__ import annotations

import json
from pathlib import Path
from xml.sax.saxutils import escape as _xml_escape

from faultray.model.components import Component, ComponentType, HealthStatus
from faultray.model.graph import InfraGraph

# ---------------------------------------------------------------------------
# Color mapping: component type -> node fill color
# ---------------------------------------------------------------------------

_TYPE_COLORS: dict[ComponentType, str] = {
    ComponentType.LOAD_BALANCER:      "#4e79a7",
    ComponentType.WEB_SERVER:         "#59a14f",
    ComponentType.APP_SERVER:         "#76b7b2",
    ComponentType.DATABASE:           "#e15759",
    ComponentType.CACHE:              "#f28e2b",
    ComponentType.QUEUE:              "#edc948",
    ComponentType.STORAGE:            "#b07aa1",
    ComponentType.DNS:                "#ff9da7",
    ComponentType.EXTERNAL_API:       "#9c755f",
    ComponentType.CUSTOM:             "#bab0ac",
    ComponentType.AI_AGENT:           "#af7aa1",
    ComponentType.LLM_ENDPOINT:       "#ff9da7",
    ComponentType.TOOL_SERVICE:       "#76b7b2",
    ComponentType.AGENT_ORCHESTRATOR: "#4e79a7",
    ComponentType.AUTOMATION:         "#edc948",
    ComponentType.SERVERLESS:         "#59a14f",
    ComponentType.SCHEDULED_JOB:      "#bab0ac",
}

_DEFAULT_COLOR = "#bab0ac"

# Edge colors per dependency type
_EDGE_COLORS: dict[str, str] = {
    "requires": "#e15759",   # red
    "optional": "#edc948",   # yellow
    "async":    "#bab0ac",   # gray
}
_EDGE_COLOR_DEFAULT = "#bab0ac"

_HEALTH_COLORS: dict[HealthStatus, str] = {
    HealthStatus.HEALTHY:    "#28a745",
    HealthStatus.DEGRADED:   "#ffc107",
    HealthStatus.OVERLOADED: "#fd7e14",
    HealthStatus.DOWN:       "#dc3545",
}


def _node_size(comp: Component, graph: InfraGraph) -> int:
    """Node radius: larger for components with more dependents."""
    dep_count = len(graph.get_dependents(comp.id))
    return 12 + min(dep_count * 4, 20)


def generate_topology_html(graph: InfraGraph, output_path: Path) -> None:
    """Generate an interactive HTML topology map.

    Args:
        graph: The infrastructure dependency graph.
        output_path: Path to write the .html file.
    """
    nodes: list[dict[str, object]] = []
    edges: list[dict[str, object]] = []

    for comp in graph.components.values():
        color = _TYPE_COLORS.get(comp.type, _DEFAULT_COLOR)
        health_color = _HEALTH_COLORS.get(comp.health, "#28a745")
        size = _node_size(comp, graph)
        dependents = graph.get_dependents(comp.id)
        dependencies = graph.get_dependencies(comp.id)
        nodes.append({
            "id": comp.id,
            "name": comp.name,
            "type": comp.type.value,
            "replicas": comp.replicas,
            "owner": comp.owner or "",
            "health": comp.health.value,
            "color": color,
            "health_color": health_color,
            "size": size,
            "dependents_count": len(dependents),
            "dependencies_count": len(dependencies),
        })

    for dep in graph.all_dependency_edges():
        dep_color = _EDGE_COLORS.get(dep.dependency_type, _EDGE_COLOR_DEFAULT)
        edges.append({
            "source": dep.source_id,
            "target": dep.target_id,
            "type": dep.dependency_type,
            "weight": dep.weight,
            "color": dep_color,
            "stroke_width": max(1.0, dep.weight * 3.0),
        })

    # Build legend entries
    used_types = {comp.type for comp in graph.components.values()}
    legend_entries = [
        {"type": t.value, "color": _TYPE_COLORS.get(t, _DEFAULT_COLOR)}
        for t in ComponentType
        if t in used_types
    ]

    nodes_json = json.dumps(nodes, ensure_ascii=False)
    edges_json = json.dumps(edges, ensure_ascii=False)
    legend_json = json.dumps(legend_entries, ensure_ascii=False)
    title = _xml_escape(f"FaultRay Topology — {len(nodes)} components")

    html = _TEMPLATE.format(
        title=title,
        nodes_json=nodes_json,
        edges_json=edges_json,
        legend_json=legend_json,
        component_count=len(nodes),
        edge_count=len(edges),
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")


# ---------------------------------------------------------------------------
# HTML template
# ---------------------------------------------------------------------------

_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{title}</title>
  <script src="https://d3js.org/d3.v7.min.js"></script>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      background: #1a1a2e;
      color: #e0e0e0;
      height: 100vh;
      overflow: hidden;
    }}
    #header {{
      position: fixed;
      top: 0; left: 0; right: 0;
      height: 52px;
      background: #16213e;
      border-bottom: 1px solid #0f3460;
      display: flex;
      align-items: center;
      padding: 0 16px;
      gap: 12px;
      z-index: 10;
    }}
    #header h1 {{
      font-size: 16px;
      font-weight: 600;
      color: #4fc3f7;
      flex: 1;
    }}
    #header .stats {{
      font-size: 12px;
      color: #90a4ae;
    }}
    #search {{
      padding: 6px 10px;
      border: 1px solid #0f3460;
      border-radius: 6px;
      background: #1a1a2e;
      color: #e0e0e0;
      font-size: 13px;
      width: 200px;
      outline: none;
    }}
    #search:focus {{
      border-color: #4fc3f7;
    }}
    #canvas {{
      position: fixed;
      top: 52px; left: 0; right: 0; bottom: 0;
    }}
    svg {{
      width: 100%;
      height: 100%;
    }}
    .node circle {{
      stroke-width: 2px;
      cursor: pointer;
      transition: opacity 0.2s;
    }}
    .node text {{
      font-size: 11px;
      fill: #e0e0e0;
      pointer-events: none;
      text-anchor: middle;
      dominant-baseline: middle;
    }}
    .link {{
      fill: none;
      stroke-opacity: 0.6;
    }}
    .link.dimmed {{
      stroke-opacity: 0.1;
    }}
    .node.dimmed circle {{
      opacity: 0.2;
    }}
    .node.dimmed text {{
      opacity: 0.2;
    }}
    .node.highlighted circle {{
      stroke: #ffffff !important;
      stroke-width: 3px;
    }}
    #tooltip {{
      position: fixed;
      background: #16213e;
      border: 1px solid #0f3460;
      border-radius: 8px;
      padding: 10px 14px;
      font-size: 12px;
      pointer-events: none;
      opacity: 0;
      transition: opacity 0.15s;
      max-width: 280px;
      z-index: 100;
      line-height: 1.6;
    }}
    #tooltip.visible {{
      opacity: 1;
    }}
    #tooltip .tt-title {{
      font-size: 13px;
      font-weight: 600;
      color: #4fc3f7;
      margin-bottom: 4px;
    }}
    #tooltip .tt-row {{
      display: flex;
      gap: 8px;
    }}
    #tooltip .tt-label {{
      color: #90a4ae;
      min-width: 90px;
    }}
    #legend {{
      position: fixed;
      bottom: 16px;
      right: 16px;
      background: #16213e;
      border: 1px solid #0f3460;
      border-radius: 8px;
      padding: 10px 14px;
      font-size: 12px;
      z-index: 10;
      max-width: 200px;
    }}
    #legend h3 {{
      font-size: 11px;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      color: #90a4ae;
      margin-bottom: 6px;
    }}
    .legend-item {{
      display: flex;
      align-items: center;
      gap: 7px;
      margin-bottom: 3px;
    }}
    .legend-dot {{
      width: 10px;
      height: 10px;
      border-radius: 50%;
      flex-shrink: 0;
    }}
    #edge-legend {{
      position: fixed;
      bottom: 16px;
      left: 16px;
      background: #16213e;
      border: 1px solid #0f3460;
      border-radius: 8px;
      padding: 10px 14px;
      font-size: 12px;
      z-index: 10;
    }}
    #edge-legend h3 {{
      font-size: 11px;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      color: #90a4ae;
      margin-bottom: 6px;
    }}
    .edge-sample {{
      display: flex;
      align-items: center;
      gap: 7px;
      margin-bottom: 3px;
    }}
    .edge-line {{
      width: 24px;
      height: 2px;
    }}
    #reset-btn {{
      padding: 5px 10px;
      background: #0f3460;
      border: 1px solid #4fc3f7;
      border-radius: 5px;
      color: #4fc3f7;
      font-size: 12px;
      cursor: pointer;
    }}
    #reset-btn:hover {{
      background: #4fc3f7;
      color: #1a1a2e;
    }}
  </style>
</head>
<body>
  <div id="header">
    <h1>FaultRay Topology Map</h1>
    <span class="stats">{component_count} components &bull; {edge_count} edges</span>
    <input id="search" type="text" placeholder="Search components..." autocomplete="off" />
    <button id="reset-btn">Reset Zoom</button>
  </div>
  <div id="canvas"></div>
  <div id="tooltip"></div>

  <div id="legend">
    <h3>Component Types</h3>
  </div>

  <div id="edge-legend">
    <h3>Dependencies</h3>
    <div class="edge-sample">
      <div class="edge-line" style="background:#e15759;"></div>
      <span>requires</span>
    </div>
    <div class="edge-sample">
      <div class="edge-line" style="background:#edc948;"></div>
      <span>optional</span>
    </div>
    <div class="edge-sample">
      <div class="edge-line" style="background:#bab0ac;"></div>
      <span>async</span>
    </div>
  </div>

  <script>
    const NODES = {nodes_json};
    const EDGES = {edges_json};
    const LEGEND_ENTRIES = {legend_json};

    // Build legend
    const legendEl = document.getElementById('legend');
    LEGEND_ENTRIES.forEach(entry => {{
      const div = document.createElement('div');
      div.className = 'legend-item';
      div.innerHTML = `
        <div class="legend-dot" style="background:${{entry.color}}"></div>
        <span>${{entry.type.replace(/_/g, ' ')}}</span>
      `;
      legendEl.appendChild(div);
    }});

    const width = window.innerWidth;
    const height = window.innerHeight - 52;

    const svg = d3.select('#canvas')
      .append('svg')
      .attr('width', width)
      .attr('height', height);

    // Zoom container
    const g = svg.append('g');

    const zoom = d3.zoom()
      .scaleExtent([0.1, 4])
      .on('zoom', (event) => g.attr('transform', event.transform));

    svg.call(zoom);

    document.getElementById('reset-btn').addEventListener('click', () => {{
      svg.transition().duration(600).call(
        zoom.transform, d3.zoomIdentity.translate(width / 2, height / 2).scale(0.8)
      );
    }});

    // Arrow marker
    svg.append('defs').selectAll('marker')
      .data(['requires', 'optional', 'async'])
      .enter().append('marker')
        .attr('id', d => `arrow-${{d}}`)
        .attr('viewBox', '0 -5 10 10')
        .attr('refX', 22)
        .attr('refY', 0)
        .attr('markerWidth', 6)
        .attr('markerHeight', 6)
        .attr('orient', 'auto')
      .append('path')
        .attr('d', 'M0,-5L10,0L0,5')
        .attr('fill', d => {{
          if (d === 'requires') return '#e15759';
          if (d === 'optional') return '#edc948';
          return '#bab0ac';
        }});

    // Force simulation
    const simulation = d3.forceSimulation(NODES)
      .force('link', d3.forceLink(EDGES).id(d => d.id).distance(120).strength(0.5))
      .force('charge', d3.forceManyBody().strength(-300))
      .force('center', d3.forceCenter(width / 2, height / 2))
      .force('collision', d3.forceCollide().radius(d => d.size + 10));

    // Edges
    const link = g.append('g')
      .attr('class', 'links')
      .selectAll('line')
      .data(EDGES)
      .enter().append('line')
        .attr('class', 'link')
        .attr('stroke', d => d.color)
        .attr('stroke-width', d => d.stroke_width)
        .attr('marker-end', d => `url(#arrow-${{d.type}})`);

    // Nodes
    const node = g.append('g')
      .attr('class', 'nodes')
      .selectAll('g')
      .data(NODES)
      .enter().append('g')
        .attr('class', 'node')
        .attr('data-id', d => d.id)
        .call(d3.drag()
          .on('start', dragstarted)
          .on('drag', dragged)
          .on('end', dragended));

    node.append('circle')
      .attr('r', d => d.size)
      .attr('fill', d => d.color)
      .attr('stroke', d => d.health_color);

    node.append('text')
      .attr('dy', d => d.size + 12)
      .text(d => d.name.length > 16 ? d.name.slice(0, 14) + '..' : d.name);

    // Tooltip
    const tooltip = document.getElementById('tooltip');

    node.on('mouseover', (event, d) => {{
      tooltip.innerHTML = `
        <div class="tt-title">${{d.name}}</div>
        <div class="tt-row"><span class="tt-label">ID:</span><span>${{d.id}}</span></div>
        <div class="tt-row"><span class="tt-label">Type:</span><span>${{d.type.replace(/_/g, ' ')}}</span></div>
        <div class="tt-row"><span class="tt-label">Replicas:</span><span>${{d.replicas}}</span></div>
        <div class="tt-row"><span class="tt-label">Health:</span><span style="color:${{d.health_color}}">${{d.health}}</span></div>
        ${{d.owner ? `<div class="tt-row"><span class="tt-label">Owner:</span><span>${{d.owner}}</span></div>` : ''}}
        <div class="tt-row"><span class="tt-label">Dependents:</span><span>${{d.dependents_count}}</span></div>
        <div class="tt-row"><span class="tt-label">Dependencies:</span><span>${{d.dependencies_count}}</span></div>
      `;
      tooltip.classList.add('visible');

      // Highlight connected nodes/links
      const connectedIds = new Set([d.id]);
      link.each(l => {{
        if (l.source.id === d.id || l.target.id === d.id) {{
          connectedIds.add(l.source.id);
          connectedIds.add(l.target.id);
        }}
      }});
      node.classed('dimmed', n => !connectedIds.has(n.id));
      node.classed('highlighted', n => n.id === d.id);
      link.classed('dimmed', l => l.source.id !== d.id && l.target.id !== d.id);
    }})
    .on('mousemove', (event) => {{
      const x = event.clientX + 12;
      const y = event.clientY + 12;
      tooltip.style.left = (x + 280 > window.innerWidth ? x - 300 : x) + 'px';
      tooltip.style.top = y + 'px';
    }})
    .on('mouseout', () => {{
      tooltip.classList.remove('visible');
      node.classed('dimmed', false);
      node.classed('highlighted', false);
      link.classed('dimmed', false);
    }});

    // Tick
    simulation.on('tick', () => {{
      link
        .attr('x1', d => d.source.x)
        .attr('y1', d => d.source.y)
        .attr('x2', d => d.target.x)
        .attr('y2', d => d.target.y);

      node.attr('transform', d => `translate(${{d.x}},${{d.y}})`);
    }});

    // Search
    const searchInput = document.getElementById('search');
    searchInput.addEventListener('input', (e) => {{
      const q = e.target.value.toLowerCase().trim();
      if (!q) {{
        node.classed('dimmed', false);
        link.classed('dimmed', false);
        return;
      }}
      const matched = new Set(
        NODES.filter(n => n.name.toLowerCase().includes(q) || n.id.toLowerCase().includes(q) || n.type.includes(q))
             .map(n => n.id)
      );
      node.classed('dimmed', d => !matched.has(d.id));
      link.classed('dimmed', l => !matched.has(l.source.id) && !matched.has(l.target.id));
    }});

    function dragstarted(event, d) {{
      if (!event.active) simulation.alphaTarget(0.3).restart();
      d.fx = d.x; d.fy = d.y;
    }}
    function dragged(event, d) {{
      d.fx = event.x; d.fy = event.y;
    }}
    function dragended(event, d) {{
      if (!event.active) simulation.alphaTarget(0);
      d.fx = null; d.fy = null;
    }}

    // Initial zoom
    svg.call(zoom.transform, d3.zoomIdentity.translate(width / 2, height / 2).scale(0.8));
  </script>
</body>
</html>
"""
