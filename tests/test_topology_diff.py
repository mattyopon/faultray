"""Tests for the Visual Topology Diff feature."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from faultray.model.components import (
    AutoScalingConfig,
    Component,
    ComponentType,
    Dependency,
    FailoverConfig,
)
from faultray.model.graph import InfraGraph
from faultray.reporter.topology_diff import (
    ComponentDiff,
    DiffType,
    EdgeDiff,
    FieldChange,
    TopologyDiffer,
    TopologyDiffResult,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_graph(*components: tuple[str, str, str, int], deps: list[tuple[str, str]] | None = None) -> InfraGraph:
    """Helper to quickly build an InfraGraph.

    Each component tuple is (id, name, type_str, replicas).
    """
    graph = InfraGraph()
    for cid, name, ctype, replicas in components:
        comp = Component(id=cid, name=name, type=ComponentType(ctype), replicas=replicas)
        graph.add_component(comp)
    for src, tgt in (deps or []):
        graph.add_dependency(Dependency(source_id=src, target_id=tgt))
    return graph


@pytest.fixture
def simple_before() -> InfraGraph:
    return _make_graph(
        ("nginx", "Nginx LB", "load_balancer", 2),
        ("app", "App Server", "app_server", 2),
        ("db", "Database", "database", 1),
        deps=[("nginx", "app"), ("app", "db")],
    )


@pytest.fixture
def simple_after() -> InfraGraph:
    return _make_graph(
        ("nginx", "Nginx LB", "load_balancer", 2),
        ("app", "App Server", "app_server", 3),  # modified: replicas 2->3
        ("db", "Database", "database", 1),
        ("redis", "Redis Cache", "cache", 2),  # added
        deps=[("nginx", "app"), ("app", "db"), ("app", "redis")],
    )


# ---------------------------------------------------------------------------
# Tests — DiffType enum
# ---------------------------------------------------------------------------


class TestDiffType:
    def test_values(self):
        assert DiffType.ADDED.value == "added"
        assert DiffType.REMOVED.value == "removed"
        assert DiffType.MODIFIED.value == "modified"
        assert DiffType.UNCHANGED.value == "unchanged"


# ---------------------------------------------------------------------------
# Tests — TopologyDiffer.diff()
# ---------------------------------------------------------------------------


class TestTopologyDiffer:
    def test_identical_graphs(self, simple_before: InfraGraph):
        differ = TopologyDiffer()
        result = differ.diff(simple_before, simple_before)

        assert len(result.components_added) == 0
        assert len(result.components_removed) == 0
        assert len(result.components_modified) == 0
        assert len(result.components_unchanged) == 3
        assert result.score_delta == 0.0
        assert result.risk_assessment == "unchanged"

    def test_added_component(self, simple_before: InfraGraph, simple_after: InfraGraph):
        differ = TopologyDiffer()
        result = differ.diff(simple_before, simple_after)

        added_ids = [c.component_id for c in result.components_added]
        assert "redis" in added_ids

    def test_removed_component(self, simple_after: InfraGraph, simple_before: InfraGraph):
        """Reverse diff: 'after' becomes 'before' so redis is removed."""
        differ = TopologyDiffer()
        result = differ.diff(simple_after, simple_before)

        removed_ids = [c.component_id for c in result.components_removed]
        assert "redis" in removed_ids

    def test_modified_component(self, simple_before: InfraGraph, simple_after: InfraGraph):
        differ = TopologyDiffer()
        result = differ.diff(simple_before, simple_after)

        modified_ids = [c.component_id for c in result.components_modified]
        assert "app" in modified_ids

        app_diff = next(c for c in result.components_modified if c.component_id == "app")
        replica_change = next(ch for ch in app_diff.changes if ch.field == "replicas")
        assert replica_change.old_value == 2
        assert replica_change.new_value == 3
        assert replica_change.impact == "positive"

    def test_edge_added(self, simple_before: InfraGraph, simple_after: InfraGraph):
        differ = TopologyDiffer()
        result = differ.diff(simple_before, simple_after)

        added_edges = [(e.source, e.target) for e in result.edges_added]
        assert ("app", "redis") in added_edges

    def test_edge_removed(self, simple_after: InfraGraph, simple_before: InfraGraph):
        differ = TopologyDiffer()
        result = differ.diff(simple_after, simple_before)

        removed_edges = [(e.source, e.target) for e in result.edges_removed]
        assert ("app", "redis") in removed_edges

    def test_empty_graphs(self):
        differ = TopologyDiffer()
        result = differ.diff(InfraGraph(), InfraGraph())

        assert len(result.components_added) == 0
        assert len(result.components_removed) == 0
        assert len(result.components_modified) == 0
        assert result.score_before == 0.0
        assert result.score_after == 0.0
        assert result.risk_assessment == "unchanged"

    def test_empty_before_nonempty_after(self):
        after = _make_graph(("app", "App", "app_server", 2))
        differ = TopologyDiffer()
        result = differ.diff(InfraGraph(), after)

        assert len(result.components_added) == 1
        assert result.components_added[0].component_id == "app"

    def test_score_delta(self, simple_before: InfraGraph, simple_after: InfraGraph):
        differ = TopologyDiffer()
        result = differ.diff(simple_before, simple_after)

        assert result.score_before == round(simple_before.resilience_score(), 1)
        assert result.score_after == round(simple_after.resilience_score(), 1)
        assert result.score_delta == round(result.score_after - result.score_before, 1)

    def test_risk_assessment_improved(self):
        """Adding replicas should improve score."""
        before = _make_graph(("app", "App", "app_server", 1), ("lb", "LB", "load_balancer", 1), deps=[("lb", "app")])
        after = _make_graph(("app", "App", "app_server", 3), ("lb", "LB", "load_balancer", 2), deps=[("lb", "app")])
        differ = TopologyDiffer()
        result = differ.diff(before, after)
        # Score may improve or stay same depending on other factors
        assert result.risk_assessment in ("improved", "unchanged")

    def test_summary_content(self, simple_before: InfraGraph, simple_after: InfraGraph):
        differ = TopologyDiffer()
        result = differ.diff(simple_before, simple_after)

        assert "Score:" in result.summary
        assert "added" in result.summary.lower() or "modified" in result.summary.lower()

    def test_feature_toggle_detection(self):
        """Detect autoscaling / failover toggle changes."""
        before = _make_graph(("app", "App", "app_server", 2))
        after_graph = _make_graph(("app", "App", "app_server", 2))
        after_graph.components["app"].autoscaling.enabled = True
        after_graph.components["app"].failover.enabled = True

        differ = TopologyDiffer()
        result = differ.diff(before, after_graph)

        assert len(result.components_modified) == 1
        fields_changed = [ch.field for ch in result.components_modified[0].changes]
        assert "autoscaling.enabled" in fields_changed
        assert "failover.enabled" in fields_changed


# ---------------------------------------------------------------------------
# Tests — Output formats
# ---------------------------------------------------------------------------


class TestOutputFormats:
    def test_unified_diff(self, simple_before: InfraGraph, simple_after: InfraGraph):
        differ = TopologyDiffer()
        result = differ.diff(simple_before, simple_after)
        unified = differ.to_unified_diff(result)

        assert "---" in unified
        assert "+++" in unified
        assert "@@" in unified
        assert "redis" in unified.lower()

    def test_mermaid_output(self, simple_before: InfraGraph, simple_after: InfraGraph):
        differ = TopologyDiffer()
        result = differ.diff(simple_before, simple_after)
        mermaid = differ.to_mermaid(result)

        assert "graph TB" in mermaid
        assert "classDef added" in mermaid
        assert "classDef removed" in mermaid
        assert "classDef modified" in mermaid
        assert "classDef unchanged" in mermaid
        assert "redis" in mermaid.lower() or "NEW" in mermaid

    def test_html_output(self, simple_before: InfraGraph, simple_after: InfraGraph):
        differ = TopologyDiffer()
        result = differ.diff(simple_before, simple_after)
        html = differ.to_html(result)

        assert "<!DOCTYPE html>" in html
        assert "Topology Diff Report" in html
        assert str(result.score_before) in html
        assert str(result.score_after) in html

    def test_to_dict(self, simple_before: InfraGraph, simple_after: InfraGraph):
        differ = TopologyDiffer()
        result = differ.diff(simple_before, simple_after)
        d = result.to_dict()

        assert "components_added" in d
        assert "components_removed" in d
        assert "components_modified" in d
        assert "score_before" in d
        assert "score_after" in d
        assert "risk_assessment" in d

        # Ensure JSON serialisable
        json.dumps(d)


# ---------------------------------------------------------------------------
# Tests — diff_files
# ---------------------------------------------------------------------------


class TestDiffFiles:
    def test_diff_yaml_files(self, tmp_path: Path):
        """Test loading and comparing two YAML files."""
        before_yaml = tmp_path / "before.yaml"
        after_yaml = tmp_path / "after.yaml"

        before_yaml.write_text("""
schema_version: "3.0"
components:
  - id: app
    name: App Server
    type: app_server
    replicas: 2
  - id: db
    name: Database
    type: database
    replicas: 1
dependencies:
  - source: app
    target: db
    type: requires
""")

        after_yaml.write_text("""
schema_version: "3.0"
components:
  - id: app
    name: App Server
    type: app_server
    replicas: 3
  - id: db
    name: Database
    type: database
    replicas: 2
  - id: cache
    name: Redis Cache
    type: cache
    replicas: 2
dependencies:
  - source: app
    target: db
    type: requires
  - source: app
    target: cache
    type: optional
""")

        differ = TopologyDiffer()
        result = differ.diff_files(before_yaml, after_yaml)

        assert len(result.components_added) == 1
        assert result.components_added[0].component_id == "cache"
        assert len(result.components_modified) >= 1

        modified_ids = [c.component_id for c in result.components_modified]
        assert "app" in modified_ids or "db" in modified_ids
