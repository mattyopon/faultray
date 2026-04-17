# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""Visual Topology Diff - Side-by-side infrastructure comparison.

Like 'git diff' but for infrastructure topologies. Shows what changed
between two versions of an infrastructure with visual highlighting.

Use cases:
- Compare prod vs staging
- Compare before/after a change
- Review infrastructure PRs
- Track infrastructure evolution
"""

from __future__ import annotations

import html as html_mod
import logging
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from faultray.model.graph import InfraGraph

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


class DiffType(str, Enum):
    """Type of change detected in a topology diff."""

    ADDED = "added"
    REMOVED = "removed"
    MODIFIED = "modified"
    UNCHANGED = "unchanged"


@dataclass
class FieldChange:
    """A single field-level change within a component."""

    field: str
    old_value: Any
    new_value: Any
    impact: str = "neutral"  # "positive", "negative", "neutral"


@dataclass
class ComponentDiff:
    """Diff result for a single component."""

    component_id: str
    component_name: str
    diff_type: DiffType
    changes: list[FieldChange] = field(default_factory=list)
    old_component: dict | None = None
    new_component: dict | None = None


@dataclass
class EdgeDiff:
    """Diff result for a single dependency edge."""

    source: str
    target: str
    diff_type: DiffType
    old_type: str | None = None
    new_type: str | None = None


@dataclass
class TopologyDiffResult:
    """Complete result of comparing two topologies."""

    components_added: list[ComponentDiff] = field(default_factory=list)
    components_removed: list[ComponentDiff] = field(default_factory=list)
    components_modified: list[ComponentDiff] = field(default_factory=list)
    components_unchanged: list[ComponentDiff] = field(default_factory=list)
    edges_added: list[EdgeDiff] = field(default_factory=list)
    edges_removed: list[EdgeDiff] = field(default_factory=list)
    score_before: float = 0.0
    score_after: float = 0.0
    score_delta: float = 0.0
    summary: str = ""
    risk_assessment: str = "unchanged"  # "improved", "degraded", "unchanged"

    def to_dict(self) -> dict:
        """Serialise result to a JSON-friendly dict."""
        return {
            "components_added": [_component_diff_dict(c) for c in self.components_added],
            "components_removed": [_component_diff_dict(c) for c in self.components_removed],
            "components_modified": [_component_diff_dict(c) for c in self.components_modified],
            "components_unchanged": [_component_diff_dict(c) for c in self.components_unchanged],
            "edges_added": [_edge_diff_dict(e) for e in self.edges_added],
            "edges_removed": [_edge_diff_dict(e) for e in self.edges_removed],
            "score_before": self.score_before,
            "score_after": self.score_after,
            "score_delta": self.score_delta,
            "summary": self.summary,
            "risk_assessment": self.risk_assessment,
        }


def _component_diff_dict(c: ComponentDiff) -> dict:
    return {
        "component_id": c.component_id,
        "component_name": c.component_name,
        "diff_type": c.diff_type.value,
        "changes": [
            {"field": ch.field, "old_value": str(ch.old_value), "new_value": str(ch.new_value), "impact": ch.impact}
            for ch in c.changes
        ],
    }


def _edge_diff_dict(e: EdgeDiff) -> dict:
    return {
        "source": e.source,
        "target": e.target,
        "diff_type": e.diff_type.value,
        "old_type": e.old_type,
        "new_type": e.new_type,
    }


# ---------------------------------------------------------------------------
# Fields we compare at the top level of a component
# ---------------------------------------------------------------------------

_IMPORTANT_FIELDS = [
    "replicas",
    "type",
    "host",
    "port",
    "health",
]

_BOOL_FEATURE_FIELDS = {
    "autoscaling.enabled": ("autoscaling", "enabled"),
    "failover.enabled": ("failover", "enabled"),
    "singleflight.enabled": ("singleflight", "enabled"),
    "cache_warming.enabled": ("cache_warming", "enabled"),
}

_NESTED_NUMERIC_FIELDS = {
    "capacity.max_rps": ("capacity", "max_rps"),
    "capacity.max_connections": ("capacity", "max_connections"),
    "capacity.timeout_seconds": ("capacity", "timeout_seconds"),
    "metrics.cpu_percent": ("metrics", "cpu_percent"),
    "metrics.memory_percent": ("metrics", "memory_percent"),
}


def _get_nested(d: dict, keys: tuple[str, ...]) -> Any:
    """Safely traverse nested dicts."""
    current = d
    for k in keys:
        if isinstance(current, dict):
            current = current.get(k)
        else:
            return None
    return current


def _assess_impact(field_name: str, old_val: Any, new_val: Any) -> str:
    """Determine whether a field change is positive, negative, or neutral."""
    if field_name == "replicas":
        if isinstance(old_val, (int, float)) and isinstance(new_val, (int, float)):
            return "positive" if new_val > old_val else "negative"
    if field_name.endswith(".enabled"):
        if new_val and not old_val:
            return "positive"
        if old_val and not new_val:
            return "negative"
    if field_name == "capacity.max_rps" or field_name == "capacity.max_connections":
        if isinstance(old_val, (int, float)) and isinstance(new_val, (int, float)):
            return "positive" if new_val > old_val else "negative"
    return "neutral"


# ---------------------------------------------------------------------------
# TopologyDiffer
# ---------------------------------------------------------------------------


class TopologyDiffer:
    """Compare two infrastructure topologies and produce a visual diff."""

    def diff(self, before: InfraGraph, after: InfraGraph) -> TopologyDiffResult:
        """Compare two InfraGraph instances."""
        before_ids = set(before.components.keys())
        after_ids = set(after.components.keys())

        added_ids = after_ids - before_ids
        removed_ids = before_ids - after_ids
        common_ids = before_ids & after_ids

        result = TopologyDiffResult()

        # Score computation
        result.score_before = round(before.resilience_score(), 1)
        result.score_after = round(after.resilience_score(), 1)
        result.score_delta = round(result.score_after - result.score_before, 1)

        # Components added
        for cid in sorted(added_ids):
            comp = after.components[cid]
            result.components_added.append(ComponentDiff(
                component_id=cid,
                component_name=comp.name,
                diff_type=DiffType.ADDED,
                new_component=comp.model_dump(),
            ))

        # Components removed
        for cid in sorted(removed_ids):
            comp = before.components[cid]
            result.components_removed.append(ComponentDiff(
                component_id=cid,
                component_name=comp.name,
                diff_type=DiffType.REMOVED,
                old_component=comp.model_dump(),
            ))

        # Components in common — check for modifications
        for cid in sorted(common_ids):
            old_comp = before.components[cid]
            new_comp = after.components[cid]
            old_dict = old_comp.model_dump()
            new_dict = new_comp.model_dump()

            changes: list[FieldChange] = []

            # Check important top-level fields
            for f in _IMPORTANT_FIELDS:
                ov = old_dict.get(f)
                nv = new_dict.get(f)
                if ov != nv:
                    changes.append(FieldChange(
                        field=f,
                        old_value=ov,
                        new_value=nv,
                        impact=_assess_impact(f, ov, nv),
                    ))

            # Check boolean feature fields
            for fname, keys in _BOOL_FEATURE_FIELDS.items():
                ov = _get_nested(old_dict, keys)
                nv = _get_nested(new_dict, keys)
                if ov != nv:
                    changes.append(FieldChange(
                        field=fname,
                        old_value=ov,
                        new_value=nv,
                        impact=_assess_impact(fname, ov, nv),
                    ))

            # Check nested numeric fields
            for fname, keys in _NESTED_NUMERIC_FIELDS.items():
                ov = _get_nested(old_dict, keys)
                nv = _get_nested(new_dict, keys)
                if ov != nv:
                    changes.append(FieldChange(
                        field=fname,
                        old_value=ov,
                        new_value=nv,
                        impact=_assess_impact(fname, ov, nv),
                    ))

            if changes:
                result.components_modified.append(ComponentDiff(
                    component_id=cid,
                    component_name=old_comp.name,
                    diff_type=DiffType.MODIFIED,
                    changes=changes,
                    old_component=old_dict,
                    new_component=new_dict,
                ))
            else:
                result.components_unchanged.append(ComponentDiff(
                    component_id=cid,
                    component_name=old_comp.name,
                    diff_type=DiffType.UNCHANGED,
                ))

        # Edge diff
        before_edges = {(d.source_id, d.target_id): d for d in before.all_dependency_edges()}
        after_edges = {(d.source_id, d.target_id): d for d in after.all_dependency_edges()}

        before_edge_keys = set(before_edges.keys())
        after_edge_keys = set(after_edges.keys())

        for key in sorted(after_edge_keys - before_edge_keys):
            dep = after_edges[key]
            result.edges_added.append(EdgeDiff(
                source=key[0],
                target=key[1],
                diff_type=DiffType.ADDED,
                new_type=dep.dependency_type,
            ))

        for key in sorted(before_edge_keys - after_edge_keys):
            dep = before_edges[key]
            result.edges_removed.append(EdgeDiff(
                source=key[0],
                target=key[1],
                diff_type=DiffType.REMOVED,
                old_type=dep.dependency_type,
            ))

        # Risk assessment
        if result.score_delta > 0:
            result.risk_assessment = "improved"
        elif result.score_delta < 0:
            result.risk_assessment = "degraded"
        else:
            result.risk_assessment = "unchanged"

        # Summary
        parts = []
        if result.components_added:
            parts.append(f"{len(result.components_added)} component(s) added")
        if result.components_removed:
            parts.append(f"{len(result.components_removed)} component(s) removed")
        if result.components_modified:
            parts.append(f"{len(result.components_modified)} component(s) modified")
        if result.edges_added:
            parts.append(f"{len(result.edges_added)} edge(s) added")
        if result.edges_removed:
            parts.append(f"{len(result.edges_removed)} edge(s) removed")
        if not parts:
            parts.append("No changes detected")

        delta_str = f"+{result.score_delta}" if result.score_delta > 0 else str(result.score_delta)
        result.summary = (
            f"Score: {result.score_before} -> {result.score_after} ({delta_str}). "
            + "; ".join(parts) + "."
        )

        return result

    def diff_files(self, before_yaml: Path, after_yaml: Path) -> TopologyDiffResult:
        """Load two YAML files and compare them."""
        from faultray.model.loader import load_yaml

        before = load_yaml(before_yaml)
        after = load_yaml(after_yaml)
        return self.diff(before, after)

    def to_unified_diff(self, result: TopologyDiffResult) -> str:
        """Produce a unified-diff-style text output."""
        lines: list[str] = []
        lines.append(f"--- before (score: {result.score_before})")
        lines.append(f"+++ after  (score: {result.score_after})")
        lines.append(f"@@ Resilience Score: {result.score_before} -> {result.score_after} "
                      f"({'+' if result.score_delta >= 0 else ''}{result.score_delta}) @@")
        lines.append("")

        for comp in result.components_removed:
            lines.append(f"- [{comp.component_id}] {comp.component_name}")

        for comp in result.components_added:
            lines.append(f"+ [{comp.component_id}] {comp.component_name}")

        for comp in result.components_modified:
            lines.append(f"~ [{comp.component_id}] {comp.component_name}")
            for ch in comp.changes:
                lines.append(f"  - {ch.field}: {ch.old_value}")
                lines.append(f"  + {ch.field}: {ch.new_value}")

        if result.edges_removed:
            lines.append("")
            for edge in result.edges_removed:
                lines.append(f"- edge: {edge.source} -> {edge.target} ({edge.old_type})")

        if result.edges_added:
            lines.append("")
            for edge in result.edges_added:
                lines.append(f"+ edge: {edge.source} -> {edge.target} ({edge.new_type})")

        lines.append("")
        lines.append(f"Risk assessment: {result.risk_assessment}")
        return "\n".join(lines)

    def to_mermaid(self, result: TopologyDiffResult) -> str:
        """Generate a color-coded Mermaid diagram."""
        lines: list[str] = [
            "graph TB",
            "    classDef added fill:#28a745,color:#fff,stroke:#28a745",
            "    classDef removed fill:#dc3545,color:#fff,stroke:#dc3545,stroke-dasharray:5",
            "    classDef modified fill:#ffc107,color:#333,stroke:#ffc107",
            "    classDef unchanged fill:#6c757d,color:#fff",
            "",
        ]

        # Collect all component IDs for edge rendering
        all_ids: set[str] = set()

        for comp in result.components_unchanged:
            cid = comp.component_id
            all_ids.add(cid)
            safe_name = comp.component_name.replace('"', "'")
            lines.append(f'    {cid}["{safe_name}"]:::unchanged')

        for comp in result.components_modified:
            cid = comp.component_id
            all_ids.add(cid)
            change_summaries = []
            for ch in comp.changes[:3]:
                change_summaries.append(f"{ch.field}: {ch.old_value}->{ch.new_value}")
            detail = ", ".join(change_summaries)
            safe_name = comp.component_name.replace('"', "'")
            label = f"{safe_name} (modified: {detail})" if detail else f"{safe_name} (modified)"
            lines.append(f'    {cid}["{label}"]:::modified')

        for comp in result.components_added:
            cid = comp.component_id
            all_ids.add(cid)
            safe_name = comp.component_name.replace('"', "'")
            lines.append(f'    {cid}["{safe_name} (NEW)"]:::added')

        for comp in result.components_removed:
            cid = comp.component_id
            all_ids.add(cid)
            safe_name = comp.component_name.replace('"', "'")
            lines.append(f'    {cid}["{safe_name} (REMOVED)"]:::removed')

        # Edges — add from both before and after
        lines.append("")

        # Edges that still exist (from after graph) or were added
        for edge in result.edges_added:
            if edge.source in all_ids and edge.target in all_ids:
                lines.append(f"    {edge.source} -->|NEW| {edge.target}")

        for edge in result.edges_removed:
            if edge.source in all_ids and edge.target in all_ids:
                lines.append(f"    {edge.source} -.->|REMOVED| {edge.target}")

        return "\n".join(lines)

    def to_html(self, result: TopologyDiffResult) -> str:
        """Generate a side-by-side HTML diff report."""
        esc = html_mod.escape

        score_color_before = _score_color(result.score_before)
        score_color_after = _score_color(result.score_after)
        delta_color = "#28a745" if result.score_delta >= 0 else "#dc3545"
        delta_str = f"+{result.score_delta}" if result.score_delta >= 0 else str(result.score_delta)

        mermaid_code = self.to_mermaid(result)

        # Build change log rows
        change_rows = []
        for comp in result.components_added:
            change_rows.append(
                f'<tr class="diff-added"><td>{esc(comp.component_id)}</td>'
                f'<td>{esc(comp.component_name)}</td><td>Added</td><td>New component</td></tr>'
            )
        for comp in result.components_removed:
            change_rows.append(
                f'<tr class="diff-removed"><td>{esc(comp.component_id)}</td>'
                f'<td>{esc(comp.component_name)}</td><td>Removed</td><td>Component removed</td></tr>'
            )
        for comp in result.components_modified:
            details = "; ".join(f"{ch.field}: {ch.old_value} -> {ch.new_value}" for ch in comp.changes)
            change_rows.append(
                f'<tr class="diff-modified"><td>{esc(comp.component_id)}</td>'
                f'<td>{esc(comp.component_name)}</td><td>Modified</td><td>{esc(details)}</td></tr>'
            )
        for edge in result.edges_added:
            change_rows.append(
                f'<tr class="diff-added"><td>{esc(edge.source)} -> {esc(edge.target)}</td>'
                f'<td>Dependency</td><td>Added</td><td>Type: {esc(edge.new_type or "unknown")}</td></tr>'
            )
        for edge in result.edges_removed:
            change_rows.append(
                f'<tr class="diff-removed"><td>{esc(edge.source)} -> {esc(edge.target)}</td>'
                f'<td>Dependency</td><td>Removed</td><td>Type: {esc(edge.old_type or "unknown")}</td></tr>'
            )

        change_table_html = "\n".join(change_rows) if change_rows else '<tr><td colspan="4">No changes detected</td></tr>'

        # Before / After component lists
        before_items = []
        for comp in result.components_removed:
            before_items.append(f'<div class="comp-item comp-removed">{esc(comp.component_name)} (removed)</div>')
        for comp in result.components_modified:
            before_items.append(f'<div class="comp-item comp-modified">{esc(comp.component_name)} (modified)</div>')
        for comp in result.components_unchanged:
            before_items.append(f'<div class="comp-item comp-unchanged">{esc(comp.component_name)}</div>')

        after_items = []
        for comp in result.components_added:
            after_items.append(f'<div class="comp-item comp-added">{esc(comp.component_name)} (new)</div>')
        for comp in result.components_modified:
            detail = ", ".join(f"{ch.field}: {ch.new_value}" for ch in comp.changes[:3])
            after_items.append(f'<div class="comp-item comp-modified">{esc(comp.component_name)} ({esc(detail)})</div>')
        for comp in result.components_unchanged:
            after_items.append(f'<div class="comp-item comp-unchanged">{esc(comp.component_name)}</div>')

        before_html = "\n".join(before_items) if before_items else "<p>No components</p>"
        after_html = "\n".join(after_items) if after_items else "<p>No components</p>"

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Topology Diff Report</title>
<script src="https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"></script>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 0; padding: 20px; background: #0d1117; color: #c9d1d9; }}
  h1, h2, h3 {{ color: #e6edf3; }}
  .score-bar {{ display: flex; gap: 40px; align-items: center; background: #161b22; padding: 20px; border-radius: 8px; margin-bottom: 20px; }}
  .score-box {{ text-align: center; }}
  .score-value {{ font-size: 2.5em; font-weight: bold; }}
  .score-label {{ font-size: 0.9em; color: #8b949e; }}
  .delta {{ font-size: 1.5em; font-weight: bold; }}
  .side-by-side {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-bottom: 20px; }}
  .panel {{ background: #161b22; padding: 16px; border-radius: 8px; }}
  .panel h3 {{ margin-top: 0; }}
  .comp-item {{ padding: 8px 12px; border-radius: 4px; margin-bottom: 4px; font-size: 0.9em; }}
  .comp-added {{ background: rgba(40, 167, 69, 0.15); border-left: 3px solid #28a745; }}
  .comp-removed {{ background: rgba(220, 53, 69, 0.15); border-left: 3px solid #dc3545; }}
  .comp-modified {{ background: rgba(255, 193, 7, 0.15); border-left: 3px solid #ffc107; }}
  .comp-unchanged {{ background: rgba(108, 117, 125, 0.1); border-left: 3px solid #6c757d; }}
  table {{ width: 100%; border-collapse: collapse; background: #161b22; border-radius: 8px; overflow: hidden; }}
  th {{ background: #21262d; padding: 10px 14px; text-align: left; font-size: 0.85em; color: #8b949e; }}
  td {{ padding: 10px 14px; border-top: 1px solid #21262d; font-size: 0.9em; }}
  .diff-added td {{ border-left: 3px solid #28a745; }}
  .diff-removed td {{ border-left: 3px solid #dc3545; }}
  .diff-modified td {{ border-left: 3px solid #ffc107; }}
  .mermaid {{ background: #fff; padding: 20px; border-radius: 8px; margin: 20px 0; }}
  .summary {{ background: #161b22; padding: 16px; border-radius: 8px; margin-bottom: 20px; }}
</style>
</head>
<body>
<h1>Topology Diff Report</h1>

<div class="score-bar">
  <div class="score-box">
    <div class="score-value" style="color: {score_color_before}">{result.score_before}</div>
    <div class="score-label">Before</div>
  </div>
  <div class="score-box">
    <div class="delta" style="color: {delta_color}">{delta_str}</div>
    <div class="score-label">Delta</div>
  </div>
  <div class="score-box">
    <div class="score-value" style="color: {score_color_after}">{result.score_after}</div>
    <div class="score-label">After</div>
  </div>
</div>

<div class="summary">
  <strong>Summary:</strong> {esc(result.summary)}<br>
  <strong>Risk Assessment:</strong> {esc(result.risk_assessment)}
</div>

<h2>Side-by-Side Comparison</h2>
<div class="side-by-side">
  <div class="panel">
    <h3>Before</h3>
    {before_html}
  </div>
  <div class="panel">
    <h3>After</h3>
    {after_html}
  </div>
</div>

<h2>Topology Diagram</h2>
<div class="mermaid">
{esc(mermaid_code)}
</div>

<h2>Change Log</h2>
<table>
  <thead>
    <tr><th>ID</th><th>Name</th><th>Change</th><th>Details</th></tr>
  </thead>
  <tbody>
    {change_table_html}
  </tbody>
</table>

<script>mermaid.initialize({{ startOnLoad: true, theme: 'default' }});</script>
</body>
</html>"""


def _score_color(score: float) -> str:
    """Return a CSS color for a resilience score."""
    if score >= 80:
        return "#28a745"
    elif score >= 60:
        return "#ffc107"
    else:
        return "#dc3545"
