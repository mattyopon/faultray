# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""Infrastructure Diff Timeline - Git-like change tracking for infrastructure topology.

Records every change to the infrastructure graph and can show diffs between
any two points in time, similar to how Git tracks source code changes.

Features:
- Automatic change detection on snapshot
- Diff between any two commits
- Blame: show all changes to a specific component
- Rollback: reconstruct graph state at any historical point
- Changelog: generate markdown changelog between commits
- Sparkline: ASCII visualization of metric trends over time
- Persistence: save/load timeline to JSONL file
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from faultray.model.components import Component, Dependency
from faultray.model.graph import InfraGraph

logger = logging.getLogger(__name__)

# Block characters for sparkline rendering (low to high)
_SPARK_CHARS = "\u2581\u2582\u2583\u2584\u2585\u2586\u2587\u2588"

# Fields to compare on Component for change detection
_TRACKED_FIELDS = [
    "replicas",
    "type",
]

# Nested boolean fields to track
_TRACKED_BOOL_FIELDS = [
    ("failover", "enabled"),
    ("autoscaling", "enabled"),
]

# Nested float/int fields to track
_TRACKED_NESTED_FIELDS = [
    ("capacity", "max_connections"),
    ("capacity", "max_rps"),
    ("metrics", "cpu_percent"),
    ("metrics", "memory_percent"),
]


class ChangeType(str, Enum):
    """Types of infrastructure changes."""

    COMPONENT_ADDED = "component_added"
    COMPONENT_REMOVED = "component_removed"
    COMPONENT_MODIFIED = "component_modified"
    EDGE_ADDED = "edge_added"
    EDGE_REMOVED = "edge_removed"
    REPLICAS_CHANGED = "replicas_changed"
    FAILOVER_TOGGLED = "failover_toggled"
    AUTOSCALING_TOGGLED = "autoscaling_toggled"
    CAPACITY_CHANGED = "capacity_changed"
    CONFIG_CHANGED = "config_changed"


@dataclass
class InfraChange:
    """A single atomic change to the infrastructure."""

    change_type: ChangeType
    component_id: str | None
    component_name: str | None
    field: str | None
    old_value: str | None
    new_value: str | None
    timestamp: str
    author: str
    message: str


@dataclass
class InfraCommit:
    """A commit representing a set of changes at a point in time."""

    commit_id: str
    changes: list[InfraChange]
    timestamp: str
    author: str
    message: str
    parent_id: str | None
    tags: list[str]
    snapshot_hash: str


@dataclass
class InfraDiff:
    """A diff between two commits."""

    from_commit: str
    to_commit: str
    changes: list[InfraChange]
    summary: str
    risk_delta: float
    components_added: int
    components_removed: int
    components_modified: int


@dataclass
class TimelineEntry:
    """An entry in the timeline log."""

    commit: InfraCommit
    resilience_score: float
    component_count: int
    edge_count: int


def _get_component_field(comp: Component, field_path: tuple[str, ...]) -> Any:
    """Get a nested field value from a Component."""
    obj: Any = comp
    for part in field_path:
        obj = getattr(obj, part, None)
        if obj is None:
            return None
    return obj


def _graph_hash(graph: InfraGraph) -> str:
    """Generate a deterministic hash of the graph state."""
    state_parts: list[str] = []

    # Sort components by id for deterministic ordering
    for cid in sorted(graph.components.keys()):
        comp = graph.components[cid]
        state_parts.append(
            f"C:{comp.id}:{comp.name}:{comp.type.value}:{comp.replicas}"
            f":{comp.failover.enabled}:{comp.autoscaling.enabled}"
        )

    # Sort edges deterministically
    edges = graph.all_dependency_edges()
    edge_keys = sorted(
        (e.source_id, e.target_id, e.dependency_type) for e in edges
    )
    for src, tgt, dtype in edge_keys:
        state_parts.append(f"E:{src}:{tgt}:{dtype}")

    raw = "|".join(state_parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _generate_commit_id(timestamp: str, changes: list[InfraChange]) -> str:
    """Generate a short commit ID from timestamp and changes."""
    parts = [timestamp]
    for ch in changes:
        parts.append(f"{ch.change_type.value}:{ch.component_id}:{ch.field}")
    raw = "|".join(parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:8]


def _change_to_dict(change: InfraChange) -> dict:
    """Serialize an InfraChange to a dictionary."""
    return {
        "change_type": change.change_type.value,
        "component_id": change.component_id,
        "component_name": change.component_name,
        "field": change.field,
        "old_value": change.old_value,
        "new_value": change.new_value,
        "timestamp": change.timestamp,
        "author": change.author,
        "message": change.message,
    }


def _change_from_dict(d: dict) -> InfraChange:
    """Deserialize an InfraChange from a dictionary."""
    return InfraChange(
        change_type=ChangeType(d["change_type"]),
        component_id=d.get("component_id"),
        component_name=d.get("component_name"),
        field=d.get("field"),
        old_value=d.get("old_value"),
        new_value=d.get("new_value"),
        timestamp=d["timestamp"],
        author=d["author"],
        message=d["message"],
    )


def _commit_to_dict(commit: InfraCommit) -> dict:
    """Serialize an InfraCommit to a dictionary."""
    return {
        "commit_id": commit.commit_id,
        "changes": [_change_to_dict(c) for c in commit.changes],
        "timestamp": commit.timestamp,
        "author": commit.author,
        "message": commit.message,
        "parent_id": commit.parent_id,
        "tags": commit.tags,
        "snapshot_hash": commit.snapshot_hash,
    }


def _commit_from_dict(d: dict) -> InfraCommit:
    """Deserialize an InfraCommit from a dictionary."""
    return InfraCommit(
        commit_id=d["commit_id"],
        changes=[_change_from_dict(c) for c in d.get("changes", [])],
        timestamp=d["timestamp"],
        author=d["author"],
        message=d["message"],
        parent_id=d.get("parent_id"),
        tags=d.get("tags", []),
        snapshot_hash=d["snapshot_hash"],
    )


def _entry_to_dict(entry: TimelineEntry) -> dict:
    """Serialize a TimelineEntry to a dictionary."""
    return {
        "commit": _commit_to_dict(entry.commit),
        "resilience_score": entry.resilience_score,
        "component_count": entry.component_count,
        "edge_count": entry.edge_count,
    }


def _entry_from_dict(d: dict) -> TimelineEntry:
    """Deserialize a TimelineEntry from a dictionary."""
    return TimelineEntry(
        commit=_commit_from_dict(d["commit"]),
        resilience_score=d["resilience_score"],
        component_count=d["component_count"],
        edge_count=d["edge_count"],
    )


def _graph_to_dict(graph: InfraGraph) -> dict:
    """Serialize a graph for snapshot storage."""
    return graph.to_dict()


def _graph_from_dict(d: dict) -> InfraGraph:
    """Reconstruct a graph from a serialized dict."""
    graph = InfraGraph()
    for c in d.get("components", []):
        graph.add_component(Component(**c))
    for dep in d.get("dependencies", []):
        graph.add_dependency(Dependency(**dep))
    return graph


class InfraTimeline:
    """Git-like change tracking system for infrastructure topology.

    Records every change to the infrastructure graph and supports
    diffing between any two points in time, blame, rollback, and
    changelog generation.
    """

    def __init__(self, storage_path: Path | None = None) -> None:
        self._storage_path = storage_path
        self._entries: list[TimelineEntry] = []
        self._snapshots: dict[str, dict] = {}  # commit_id -> graph dict

        # Load persisted data if storage path exists
        if self._storage_path and self._storage_path.exists():
            self._load()

    def snapshot(
        self,
        graph: InfraGraph,
        author: str,
        message: str,
        tags: list[str] | None = None,
    ) -> InfraCommit:
        """Take a snapshot of the current graph state and detect changes.

        Compares against the previous snapshot (if any) and records
        all detected changes as an InfraCommit.

        Args:
            graph: The current infrastructure graph.
            author: Who made this change.
            message: Description of the change.
            tags: Optional tags for this commit.

        Returns:
            The InfraCommit representing this snapshot.
        """
        now = datetime.now(timezone.utc).isoformat()
        snapshot_hash = _graph_hash(graph)

        # Detect changes from previous snapshot
        if self._entries:
            prev_commit_id = self._entries[-1].commit.commit_id
            prev_graph_dict = self._snapshots.get(prev_commit_id)
            if prev_graph_dict is not None:
                old_graph = _graph_from_dict(prev_graph_dict)
                changes = self.diff_graphs(old_graph, graph)
            else:
                changes = []
            parent_id = prev_commit_id
        else:
            # First snapshot: all components are "added"
            changes = self._initial_changes(graph, now, author, message)
            parent_id = None

        # Set timestamp/author/message on all changes
        for ch in changes:
            ch.timestamp = now
            ch.author = author
            ch.message = message

        commit_id = _generate_commit_id(now, changes)
        commit = InfraCommit(
            commit_id=commit_id,
            changes=changes,
            timestamp=now,
            author=author,
            message=message,
            parent_id=parent_id,
            tags=list(tags) if tags else [],
            snapshot_hash=snapshot_hash,
        )

        # Calculate metrics
        resilience_score = graph.resilience_score()
        component_count = len(graph.components)
        edge_count = len(graph.all_dependency_edges())

        entry = TimelineEntry(
            commit=commit,
            resilience_score=resilience_score,
            component_count=component_count,
            edge_count=edge_count,
        )

        self._entries.append(entry)
        self._snapshots[commit_id] = _graph_to_dict(graph)

        # Persist if storage path configured
        if self._storage_path:
            self._save()

        return commit

    def diff(self, from_id: str, to_id: str) -> InfraDiff:
        """Compute a diff between two commits.

        Args:
            from_id: The source commit ID.
            to_id: The target commit ID.

        Returns:
            An InfraDiff describing all changes between the two commits.

        Raises:
            KeyError: If either commit ID is not found.
        """
        from_graph_dict = self._snapshots.get(from_id)
        to_graph_dict = self._snapshots.get(to_id)

        if from_graph_dict is None:
            raise KeyError(f"Commit not found: {from_id}")
        if to_graph_dict is None:
            raise KeyError(f"Commit not found: {to_id}")

        old_graph = _graph_from_dict(from_graph_dict)
        new_graph = _graph_from_dict(to_graph_dict)

        changes = self.diff_graphs(old_graph, new_graph)

        # Count changes by category
        added = sum(
            1 for c in changes if c.change_type == ChangeType.COMPONENT_ADDED
        )
        removed = sum(
            1 for c in changes if c.change_type == ChangeType.COMPONENT_REMOVED
        )
        modified = sum(
            1
            for c in changes
            if c.change_type
            not in (
                ChangeType.COMPONENT_ADDED,
                ChangeType.COMPONENT_REMOVED,
                ChangeType.EDGE_ADDED,
                ChangeType.EDGE_REMOVED,
            )
        )

        # Calculate resilience delta
        from_entry = self._find_entry(from_id)
        to_entry = self._find_entry(to_id)
        risk_delta = 0.0
        if from_entry and to_entry:
            risk_delta = to_entry.resilience_score - from_entry.resilience_score

        # Build summary
        parts: list[str] = []
        if added:
            parts.append(f"{added} component(s) added")
        if removed:
            parts.append(f"{removed} component(s) removed")
        if modified:
            parts.append(f"{modified} modification(s)")
        edge_added = sum(
            1 for c in changes if c.change_type == ChangeType.EDGE_ADDED
        )
        edge_removed = sum(
            1 for c in changes if c.change_type == ChangeType.EDGE_REMOVED
        )
        if edge_added:
            parts.append(f"{edge_added} edge(s) added")
        if edge_removed:
            parts.append(f"{edge_removed} edge(s) removed")

        summary = "; ".join(parts) if parts else "No changes"

        return InfraDiff(
            from_commit=from_id,
            to_commit=to_id,
            changes=changes,
            summary=summary,
            risk_delta=risk_delta,
            components_added=added,
            components_removed=removed,
            components_modified=modified,
        )

    def diff_graphs(
        self, old_graph: InfraGraph, new_graph: InfraGraph
    ) -> list[InfraChange]:
        """Compare two graphs directly and return detected changes.

        Args:
            old_graph: The previous graph state.
            new_graph: The current graph state.

        Returns:
            List of InfraChange objects describing all differences.
        """
        changes: list[InfraChange] = []
        now = datetime.now(timezone.utc).isoformat()

        old_ids = set(old_graph.components.keys())
        new_ids = set(new_graph.components.keys())

        # Added components
        for cid in sorted(new_ids - old_ids):
            comp = new_graph.components[cid]
            changes.append(
                InfraChange(
                    change_type=ChangeType.COMPONENT_ADDED,
                    component_id=cid,
                    component_name=comp.name,
                    field=None,
                    old_value=None,
                    new_value=f"{comp.type.value}, {comp.replicas} replicas",
                    timestamp=now,
                    author="",
                    message="",
                )
            )

        # Removed components
        for cid in sorted(old_ids - new_ids):
            comp = old_graph.components[cid]
            changes.append(
                InfraChange(
                    change_type=ChangeType.COMPONENT_REMOVED,
                    component_id=cid,
                    component_name=comp.name,
                    field=None,
                    old_value=f"{comp.type.value}, {comp.replicas} replicas",
                    new_value=None,
                    timestamp=now,
                    author="",
                    message="",
                )
            )

        # Modified components (compare shared components)
        for cid in sorted(old_ids & new_ids):
            old_comp = old_graph.components[cid]
            new_comp = new_graph.components[cid]

            # Check replicas
            if old_comp.replicas != new_comp.replicas:
                changes.append(
                    InfraChange(
                        change_type=ChangeType.REPLICAS_CHANGED,
                        component_id=cid,
                        component_name=new_comp.name,
                        field="replicas",
                        old_value=str(old_comp.replicas),
                        new_value=str(new_comp.replicas),
                        timestamp=now,
                        author="",
                        message="",
                    )
                )

            # Check failover toggle
            if old_comp.failover.enabled != new_comp.failover.enabled:
                changes.append(
                    InfraChange(
                        change_type=ChangeType.FAILOVER_TOGGLED,
                        component_id=cid,
                        component_name=new_comp.name,
                        field="failover.enabled",
                        old_value=str(old_comp.failover.enabled),
                        new_value=str(new_comp.failover.enabled),
                        timestamp=now,
                        author="",
                        message="",
                    )
                )

            # Check autoscaling toggle
            if old_comp.autoscaling.enabled != new_comp.autoscaling.enabled:
                changes.append(
                    InfraChange(
                        change_type=ChangeType.AUTOSCALING_TOGGLED,
                        component_id=cid,
                        component_name=new_comp.name,
                        field="autoscaling.enabled",
                        old_value=str(old_comp.autoscaling.enabled),
                        new_value=str(new_comp.autoscaling.enabled),
                        timestamp=now,
                        author="",
                        message="",
                    )
                )

            # Check capacity fields
            for parent_attr, child_attr in _TRACKED_NESTED_FIELDS:
                old_val = _get_component_field(old_comp, (parent_attr, child_attr))
                new_val = _get_component_field(new_comp, (parent_attr, child_attr))
                if old_val != new_val:
                    change_type = (
                        ChangeType.CAPACITY_CHANGED
                        if parent_attr == "capacity"
                        else ChangeType.CONFIG_CHANGED
                    )
                    changes.append(
                        InfraChange(
                            change_type=change_type,
                            component_id=cid,
                            component_name=new_comp.name,
                            field=f"{parent_attr}.{child_attr}",
                            old_value=str(old_val),
                            new_value=str(new_val),
                            timestamp=now,
                            author="",
                            message="",
                        )
                    )

            # Check type change
            if old_comp.type != new_comp.type:
                changes.append(
                    InfraChange(
                        change_type=ChangeType.COMPONENT_MODIFIED,
                        component_id=cid,
                        component_name=new_comp.name,
                        field="type",
                        old_value=old_comp.type.value,
                        new_value=new_comp.type.value,
                        timestamp=now,
                        author="",
                        message="",
                    )
                )

        # Compare edges
        old_edges = {
            (e.source_id, e.target_id) for e in old_graph.all_dependency_edges()
        }
        new_edges = {
            (e.source_id, e.target_id) for e in new_graph.all_dependency_edges()
        }

        for src, tgt in sorted(new_edges - old_edges):
            changes.append(
                InfraChange(
                    change_type=ChangeType.EDGE_ADDED,
                    component_id=None,
                    component_name=None,
                    field=f"{src} -> {tgt}",
                    old_value=None,
                    new_value=f"{src} -> {tgt}",
                    timestamp=now,
                    author="",
                    message="",
                )
            )

        for src, tgt in sorted(old_edges - new_edges):
            changes.append(
                InfraChange(
                    change_type=ChangeType.EDGE_REMOVED,
                    component_id=None,
                    component_name=None,
                    field=f"{src} -> {tgt}",
                    old_value=f"{src} -> {tgt}",
                    new_value=None,
                    timestamp=now,
                    author="",
                    message="",
                )
            )

        return changes

    def log(self, limit: int = 20) -> list[TimelineEntry]:
        """Show recent timeline history.

        Args:
            limit: Maximum number of entries to return (most recent first).

        Returns:
            List of TimelineEntry objects, newest first.
        """
        return list(reversed(self._entries[-limit:]))

    def get_commit(self, commit_id: str) -> InfraCommit:
        """Get a specific commit by ID.

        Args:
            commit_id: The commit ID to look up.

        Returns:
            The InfraCommit.

        Raises:
            KeyError: If the commit ID is not found.
        """
        entry = self._find_entry(commit_id)
        if entry is None:
            raise KeyError(f"Commit not found: {commit_id}")
        return entry.commit

    def search(self, query: str) -> list[InfraCommit]:
        """Search commits by message content.

        Args:
            query: Case-insensitive search string.

        Returns:
            List of matching InfraCommit objects.
        """
        query_lower = query.lower()
        results: list[InfraCommit] = []
        for entry in self._entries:
            if query_lower in entry.commit.message.lower():
                results.append(entry.commit)
        return results

    def tag(self, commit_id: str, tag: str) -> None:
        """Add a tag to an existing commit.

        Args:
            commit_id: The commit ID to tag.
            tag: The tag string to add.

        Raises:
            KeyError: If the commit ID is not found.
        """
        entry = self._find_entry(commit_id)
        if entry is None:
            raise KeyError(f"Commit not found: {commit_id}")
        if tag not in entry.commit.tags:
            entry.commit.tags.append(tag)

        # Persist updated state
        if self._storage_path:
            self._save()

    def rollback_to(self, commit_id: str) -> InfraGraph:
        """Reconstruct the infrastructure graph at a given commit.

        Args:
            commit_id: The commit ID to roll back to.

        Returns:
            The reconstructed InfraGraph.

        Raises:
            KeyError: If the commit ID or its snapshot is not found.
        """
        graph_dict = self._snapshots.get(commit_id)
        if graph_dict is None:
            raise KeyError(f"Snapshot not found for commit: {commit_id}")
        return _graph_from_dict(graph_dict)

    def blame(self, component_id: str) -> list[InfraChange]:
        """Show all changes that affected a specific component.

        Args:
            component_id: The component ID to trace.

        Returns:
            List of InfraChange objects affecting this component,
            in chronological order.
        """
        results: list[InfraChange] = []
        for entry in self._entries:
            for change in entry.commit.changes:
                if change.component_id == component_id:
                    results.append(change)
        return results

    def changelog(
        self, from_id: str | None = None, to_id: str | None = None
    ) -> str:
        """Generate a markdown changelog between two commits.

        If from_id is None, starts from the beginning.
        If to_id is None, goes to the latest commit.

        Args:
            from_id: Starting commit ID (exclusive), or None for beginning.
            to_id: Ending commit ID (inclusive), or None for latest.

        Returns:
            Markdown-formatted changelog string.
        """
        if not self._entries:
            return "# Changelog\n\nNo entries.\n"

        # Determine range
        start_idx = 0
        end_idx = len(self._entries) - 1

        if from_id is not None:
            for i, entry in enumerate(self._entries):
                if entry.commit.commit_id == from_id:
                    start_idx = i + 1  # exclusive
                    break

        if to_id is not None:
            for i, entry in enumerate(self._entries):
                if entry.commit.commit_id == to_id:
                    end_idx = i
                    break

        if start_idx > end_idx:
            return "# Changelog\n\nNo entries in range.\n"

        lines: list[str] = ["# Changelog\n"]

        for i in range(end_idx, start_idx - 1, -1):
            entry = self._entries[i]
            commit = entry.commit

            # Header line
            ts_short = commit.timestamp[:10] if len(commit.timestamp) >= 10 else commit.timestamp
            tag_str = ""
            if commit.tags:
                tag_str = " (" + ", ".join(f"tag: {t}" for t in commit.tags) + ")"
            lines.append(f"## [{commit.commit_id}] - {ts_short}{tag_str}\n")

            if commit.message:
                lines.append(f"*{commit.message}*\n")

            # Group changes
            added: list[InfraChange] = []
            changed: list[InfraChange] = []
            removed: list[InfraChange] = []
            edges: list[InfraChange] = []

            for ch in commit.changes:
                if ch.change_type == ChangeType.COMPONENT_ADDED:
                    added.append(ch)
                elif ch.change_type == ChangeType.COMPONENT_REMOVED:
                    removed.append(ch)
                elif ch.change_type in (
                    ChangeType.EDGE_ADDED,
                    ChangeType.EDGE_REMOVED,
                ):
                    edges.append(ch)
                else:
                    changed.append(ch)

            if added:
                lines.append("### Added\n")
                for ch in added:
                    lines.append(
                        f"- Component: {ch.component_name or ch.component_id}"
                        f" ({ch.new_value})\n"
                    )

            if changed:
                lines.append("### Changed\n")
                for ch in changed:
                    cname = ch.component_name or ch.component_id or "unknown"
                    field_name = ch.field or ch.change_type.value
                    old_v = ch.old_value or "N/A"
                    new_v = ch.new_value or "N/A"
                    lines.append(
                        f"- {cname}: {field_name} {old_v} \u2192 {new_v}\n"
                    )

            if removed:
                lines.append("### Removed\n")
                for ch in removed:
                    lines.append(
                        f"- {ch.component_name or ch.component_id}\n"
                    )

            if edges:
                lines.append("### Edges\n")
                for ch in edges:
                    action = "Added" if ch.change_type == ChangeType.EDGE_ADDED else "Removed"
                    lines.append(f"- {action}: {ch.field}\n")

            # Resilience impact
            if i > 0:
                prev_score = self._entries[i - 1].resilience_score
                curr_score = entry.resilience_score
                delta = curr_score - prev_score
                sign = "+" if delta >= 0 else ""
                lines.append(
                    f"\n**Resilience Impact:** {sign}{delta:.0f} points"
                    f" ({prev_score:.0f} \u2192 {curr_score:.0f})\n"
                )
            else:
                lines.append(
                    f"\n**Resilience Score:** {entry.resilience_score:.0f}\n"
                )

            lines.append("")

        return "\n".join(lines)

    def get_timeline_sparkline(
        self, field: str = "resilience_score", width: int = 40
    ) -> str:
        """Generate an ASCII sparkline of a metric over time.

        Args:
            field: The metric to plot. Supported: 'resilience_score',
                   'component_count', 'edge_count'.
            width: Maximum number of characters in the sparkline.

        Returns:
            A string of block characters representing the trend.
        """
        if not self._entries:
            return ""

        # Extract values
        values: list[float] = []
        for entry in self._entries:
            if field == "resilience_score":
                values.append(entry.resilience_score)
            elif field == "component_count":
                values.append(float(entry.component_count))
            elif field == "edge_count":
                values.append(float(entry.edge_count))
            else:
                values.append(0.0)

        if not values:
            return ""

        # Downsample if necessary
        if len(values) > width:
            step = len(values) / width
            sampled: list[float] = []
            for i in range(width):
                idx = int(i * step)
                sampled.append(values[idx])
            values = sampled

        # Normalize to sparkline characters
        min_val = min(values)
        max_val = max(values)
        val_range = max_val - min_val

        chars: list[str] = []
        for v in values:
            if val_range == 0:
                idx = len(_SPARK_CHARS) - 1
            else:
                normalized = (v - min_val) / val_range
                idx = int(normalized * (len(_SPARK_CHARS) - 1))
                idx = max(0, min(len(_SPARK_CHARS) - 1, idx))
            chars.append(_SPARK_CHARS[idx])

        return "".join(chars)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _initial_changes(
        self, graph: InfraGraph, timestamp: str, author: str, message: str
    ) -> list[InfraChange]:
        """Generate changes for the very first snapshot (all components added)."""
        changes: list[InfraChange] = []

        for cid in sorted(graph.components.keys()):
            comp = graph.components[cid]
            changes.append(
                InfraChange(
                    change_type=ChangeType.COMPONENT_ADDED,
                    component_id=cid,
                    component_name=comp.name,
                    field=None,
                    old_value=None,
                    new_value=f"{comp.type.value}, {comp.replicas} replicas",
                    timestamp=timestamp,
                    author=author,
                    message=message,
                )
            )

        for edge in graph.all_dependency_edges():
            changes.append(
                InfraChange(
                    change_type=ChangeType.EDGE_ADDED,
                    component_id=None,
                    component_name=None,
                    field=f"{edge.source_id} -> {edge.target_id}",
                    old_value=None,
                    new_value=f"{edge.source_id} -> {edge.target_id}",
                    timestamp=timestamp,
                    author=author,
                    message=message,
                )
            )

        return changes

    def _find_entry(self, commit_id: str) -> TimelineEntry | None:
        """Find a timeline entry by commit ID."""
        for entry in self._entries:
            if entry.commit.commit_id == commit_id:
                return entry
        return None

    def _save(self) -> None:
        """Persist timeline data to JSONL file."""
        if not self._storage_path:
            return

        self._storage_path.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "entries": [_entry_to_dict(e) for e in self._entries],
            "snapshots": self._snapshots,
        }

        self._storage_path.write_text(
            json.dumps(data, default=str, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    def _load(self) -> None:
        """Load timeline data from JSONL file."""
        if not self._storage_path or not self._storage_path.exists():
            return

        try:
            raw = self._storage_path.read_text(encoding="utf-8").strip()
            if not raw:
                return

            data = json.loads(raw)
            self._entries = [
                _entry_from_dict(e) for e in data.get("entries", [])
            ]
            self._snapshots = data.get("snapshots", {})
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            logger.warning("Failed to load timeline data: %s", exc)
            self._entries = []
            self._snapshots = {}
