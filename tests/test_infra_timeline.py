"""Tests for InfraTimeline - Git-like change tracking for infrastructure topology."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from infrasim.model.components import Component, ComponentType, Dependency
from infrasim.model.graph import InfraGraph
from infrasim.simulator.infra_timeline import (
    ChangeType,
    InfraChange,
    InfraCommit,
    InfraDiff,
    InfraTimeline,
    TimelineEntry,
    _change_from_dict,
    _change_to_dict,
    _commit_from_dict,
    _commit_to_dict,
    _entry_from_dict,
    _entry_to_dict,
    _generate_commit_id,
    _get_component_field,
    _graph_hash,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_component(
    cid: str,
    name: str,
    ctype: ComponentType = ComponentType.APP_SERVER,
    replicas: int = 1,
    failover: bool = False,
    autoscaling: bool = False,
) -> Component:
    """Create a Component with common defaults for testing."""
    comp = Component(id=cid, name=name, type=ctype, replicas=replicas)
    if failover:
        comp.failover.enabled = True
    if autoscaling:
        comp.autoscaling.enabled = True
    return comp


def _make_graph_with_components(*components: Component) -> InfraGraph:
    """Build an InfraGraph from a list of components."""
    g = InfraGraph()
    for c in components:
        g.add_component(c)
    return g


def _basic_graph() -> InfraGraph:
    """Create a small graph: lb -> api -> db."""
    g = InfraGraph()
    g.add_component(_make_component("lb", "Load Balancer", ComponentType.LOAD_BALANCER, replicas=2))
    g.add_component(_make_component("api", "API Server", ComponentType.APP_SERVER, replicas=2))
    g.add_component(_make_component("db", "Database", ComponentType.DATABASE, replicas=1))
    g.add_dependency(Dependency(source_id="lb", target_id="api", dependency_type="requires"))
    g.add_dependency(Dependency(source_id="api", target_id="db", dependency_type="requires"))
    return g


def _modified_graph() -> InfraGraph:
    """Create a graph with changes from _basic_graph: db replicas changed, cache added, lb removed."""
    g = InfraGraph()
    g.add_component(_make_component("api", "API Server", ComponentType.APP_SERVER, replicas=3))
    g.add_component(_make_component("db", "Database", ComponentType.DATABASE, replicas=3, failover=True))
    g.add_component(_make_component("cache", "Redis Cache", ComponentType.CACHE, replicas=2))
    g.add_dependency(Dependency(source_id="api", target_id="db", dependency_type="requires"))
    g.add_dependency(Dependency(source_id="api", target_id="cache", dependency_type="optional"))
    return g


# ===========================================================================
# Test: ChangeType enum
# ===========================================================================

class TestChangeType:
    def test_all_values_exist(self):
        expected = {
            "component_added", "component_removed", "component_modified",
            "edge_added", "edge_removed", "replicas_changed",
            "failover_toggled", "autoscaling_toggled", "capacity_changed",
            "config_changed",
        }
        actual = {ct.value for ct in ChangeType}
        assert actual == expected

    def test_string_enum(self):
        assert ChangeType.COMPONENT_ADDED == "component_added"
        assert isinstance(ChangeType.EDGE_REMOVED, str)


# ===========================================================================
# Test: Data classes
# ===========================================================================

class TestDataClasses:
    def test_infra_change_creation(self):
        ch = InfraChange(
            change_type=ChangeType.REPLICAS_CHANGED,
            component_id="api",
            component_name="API Server",
            field="replicas",
            old_value="1",
            new_value="3",
            timestamp="2024-01-15T00:00:00Z",
            author="admin",
            message="scale up api",
        )
        assert ch.change_type == ChangeType.REPLICAS_CHANGED
        assert ch.component_id == "api"
        assert ch.old_value == "1"
        assert ch.new_value == "3"

    def test_infra_commit_creation(self):
        commit = InfraCommit(
            commit_id="abcd1234",
            changes=[],
            timestamp="2024-01-15T00:00:00Z",
            author="admin",
            message="initial",
            parent_id=None,
            tags=["v1.0"],
            snapshot_hash="abc123",
        )
        assert commit.commit_id == "abcd1234"
        assert commit.parent_id is None
        assert commit.tags == ["v1.0"]

    def test_infra_diff_creation(self):
        diff = InfraDiff(
            from_commit="aaa",
            to_commit="bbb",
            changes=[],
            summary="No changes",
            risk_delta=0.0,
            components_added=0,
            components_removed=0,
            components_modified=0,
        )
        assert diff.summary == "No changes"
        assert diff.risk_delta == 0.0

    def test_timeline_entry_creation(self):
        commit = InfraCommit(
            commit_id="x", changes=[], timestamp="t", author="a",
            message="m", parent_id=None, tags=[], snapshot_hash="h",
        )
        entry = TimelineEntry(
            commit=commit, resilience_score=85.0,
            component_count=5, edge_count=4,
        )
        assert entry.resilience_score == 85.0
        assert entry.component_count == 5


# ===========================================================================
# Test: Snapshot creation and change detection
# ===========================================================================

class TestSnapshotCreation:
    def test_first_snapshot_detects_all_as_added(self):
        timeline = InfraTimeline()
        graph = _basic_graph()
        commit = timeline.snapshot(graph, "admin", "initial setup")

        # Should detect 3 components added + 2 edges added
        added = [c for c in commit.changes if c.change_type == ChangeType.COMPONENT_ADDED]
        edges = [c for c in commit.changes if c.change_type == ChangeType.EDGE_ADDED]
        assert len(added) == 3
        assert len(edges) == 2
        assert commit.parent_id is None

    def test_first_snapshot_component_ids(self):
        timeline = InfraTimeline()
        graph = _basic_graph()
        commit = timeline.snapshot(graph, "admin", "initial")

        comp_ids = {c.component_id for c in commit.changes if c.component_id}
        assert "lb" in comp_ids
        assert "api" in comp_ids
        assert "db" in comp_ids

    def test_second_snapshot_detects_changes(self):
        timeline = InfraTimeline()
        g1 = _basic_graph()
        c1 = timeline.snapshot(g1, "admin", "initial")

        g2 = _modified_graph()
        c2 = timeline.snapshot(g2, "admin", "scale and restructure")

        assert c2.parent_id == c1.commit_id

        # Check for added/removed/modified
        change_types = {c.change_type for c in c2.changes}
        assert ChangeType.COMPONENT_ADDED in change_types  # cache added
        assert ChangeType.COMPONENT_REMOVED in change_types  # lb removed
        assert ChangeType.REPLICAS_CHANGED in change_types  # db replicas, api replicas

    def test_snapshot_no_changes_between_identical_graphs(self):
        timeline = InfraTimeline()
        g = _basic_graph()
        c1 = timeline.snapshot(g, "admin", "initial")

        # Snapshot the exact same graph again
        g2 = _basic_graph()
        c2 = timeline.snapshot(g2, "admin", "no changes")

        # Should have no meaningful changes (diff_graphs returns empty)
        assert len(c2.changes) == 0

    def test_snapshot_sets_timestamp_and_author_on_changes(self):
        timeline = InfraTimeline()
        graph = _basic_graph()
        commit = timeline.snapshot(graph, "deploy-bot", "deploy v1")

        for ch in commit.changes:
            assert ch.author == "deploy-bot"
            assert ch.message == "deploy v1"
            assert len(ch.timestamp) > 0

    def test_snapshot_hash_is_deterministic(self):
        g1 = _basic_graph()
        g2 = _basic_graph()
        assert _graph_hash(g1) == _graph_hash(g2)

    def test_snapshot_hash_changes_with_different_graph(self):
        g1 = _basic_graph()
        g2 = _modified_graph()
        assert _graph_hash(g1) != _graph_hash(g2)


# ===========================================================================
# Test: Diff between commits
# ===========================================================================

class TestDiff:
    def test_diff_add_remove_modify(self):
        timeline = InfraTimeline()
        g1 = _basic_graph()
        c1 = timeline.snapshot(g1, "admin", "v1")

        g2 = _modified_graph()
        c2 = timeline.snapshot(g2, "admin", "v2")

        diff = timeline.diff(c1.commit_id, c2.commit_id)

        assert diff.from_commit == c1.commit_id
        assert diff.to_commit == c2.commit_id
        assert diff.components_added >= 1  # cache
        assert diff.components_removed >= 1  # lb
        assert diff.components_modified >= 1  # replicas changes

    def test_diff_summary_text(self):
        timeline = InfraTimeline()
        g1 = _basic_graph()
        c1 = timeline.snapshot(g1, "admin", "v1")

        g2 = _modified_graph()
        c2 = timeline.snapshot(g2, "admin", "v2")

        diff = timeline.diff(c1.commit_id, c2.commit_id)
        assert "added" in diff.summary.lower() or "removed" in diff.summary.lower()

    def test_diff_risk_delta(self):
        timeline = InfraTimeline()
        g1 = _basic_graph()
        c1 = timeline.snapshot(g1, "admin", "v1")

        g2 = _modified_graph()
        c2 = timeline.snapshot(g2, "admin", "v2")

        diff = timeline.diff(c1.commit_id, c2.commit_id)
        # risk_delta should be a number (could be positive or negative)
        assert isinstance(diff.risk_delta, float)

    def test_diff_no_changes(self):
        timeline = InfraTimeline()
        g = _basic_graph()
        c1 = timeline.snapshot(g, "admin", "v1")

        g2 = _basic_graph()
        c2 = timeline.snapshot(g2, "admin", "v2")

        diff = timeline.diff(c1.commit_id, c2.commit_id)
        assert diff.components_added == 0
        assert diff.components_removed == 0
        assert diff.components_modified == 0
        assert "No changes" in diff.summary

    def test_diff_invalid_commit_raises_keyerror(self):
        timeline = InfraTimeline()
        g = _basic_graph()
        c1 = timeline.snapshot(g, "admin", "v1")

        with pytest.raises(KeyError):
            timeline.diff(c1.commit_id, "nonexistent")

        with pytest.raises(KeyError):
            timeline.diff("nonexistent", c1.commit_id)

    def test_diff_edge_changes(self):
        timeline = InfraTimeline()
        g1 = _basic_graph()
        c1 = timeline.snapshot(g1, "admin", "v1")

        g2 = _modified_graph()
        c2 = timeline.snapshot(g2, "admin", "v2")

        diff = timeline.diff(c1.commit_id, c2.commit_id)

        edge_changes = [
            c for c in diff.changes
            if c.change_type in (ChangeType.EDGE_ADDED, ChangeType.EDGE_REMOVED)
        ]
        assert len(edge_changes) > 0


# ===========================================================================
# Test: Direct graph comparison
# ===========================================================================

class TestDiffGraphs:
    def test_empty_to_populated(self):
        timeline = InfraTimeline()
        old_g = InfraGraph()
        new_g = _basic_graph()

        changes = timeline.diff_graphs(old_g, new_g)
        added = [c for c in changes if c.change_type == ChangeType.COMPONENT_ADDED]
        assert len(added) == 3

    def test_populated_to_empty(self):
        timeline = InfraTimeline()
        old_g = _basic_graph()
        new_g = InfraGraph()

        changes = timeline.diff_graphs(old_g, new_g)
        removed = [c for c in changes if c.change_type == ChangeType.COMPONENT_REMOVED]
        assert len(removed) == 3

    def test_detect_replicas_change(self):
        timeline = InfraTimeline()
        g1 = _make_graph_with_components(
            _make_component("api", "API", replicas=1),
        )
        g2 = _make_graph_with_components(
            _make_component("api", "API", replicas=3),
        )

        changes = timeline.diff_graphs(g1, g2)
        replica_changes = [c for c in changes if c.change_type == ChangeType.REPLICAS_CHANGED]
        assert len(replica_changes) == 1
        assert replica_changes[0].old_value == "1"
        assert replica_changes[0].new_value == "3"

    def test_detect_failover_toggle(self):
        timeline = InfraTimeline()
        g1 = _make_graph_with_components(
            _make_component("db", "DB", failover=False),
        )
        g2 = _make_graph_with_components(
            _make_component("db", "DB", failover=True),
        )

        changes = timeline.diff_graphs(g1, g2)
        failover_changes = [c for c in changes if c.change_type == ChangeType.FAILOVER_TOGGLED]
        assert len(failover_changes) == 1
        assert failover_changes[0].old_value == "False"
        assert failover_changes[0].new_value == "True"

    def test_detect_autoscaling_toggle(self):
        timeline = InfraTimeline()
        g1 = _make_graph_with_components(
            _make_component("api", "API", autoscaling=False),
        )
        g2 = _make_graph_with_components(
            _make_component("api", "API", autoscaling=True),
        )

        changes = timeline.diff_graphs(g1, g2)
        as_changes = [c for c in changes if c.change_type == ChangeType.AUTOSCALING_TOGGLED]
        assert len(as_changes) == 1

    def test_detect_type_change(self):
        timeline = InfraTimeline()
        g1 = _make_graph_with_components(
            _make_component("svc", "Service", ctype=ComponentType.APP_SERVER),
        )
        g2 = _make_graph_with_components(
            _make_component("svc", "Service", ctype=ComponentType.WEB_SERVER),
        )

        changes = timeline.diff_graphs(g1, g2)
        type_changes = [c for c in changes if c.change_type == ChangeType.COMPONENT_MODIFIED]
        assert len(type_changes) == 1
        assert type_changes[0].field == "type"
        assert type_changes[0].old_value == "app_server"
        assert type_changes[0].new_value == "web_server"

    def test_detect_edge_added(self):
        timeline = InfraTimeline()
        g1 = _make_graph_with_components(
            _make_component("a", "A"),
            _make_component("b", "B"),
        )
        g2 = _make_graph_with_components(
            _make_component("a", "A"),
            _make_component("b", "B"),
        )
        g2.add_dependency(Dependency(source_id="a", target_id="b", dependency_type="requires"))

        changes = timeline.diff_graphs(g1, g2)
        edge_added = [c for c in changes if c.change_type == ChangeType.EDGE_ADDED]
        assert len(edge_added) == 1
        assert "a -> b" in (edge_added[0].field or "")

    def test_detect_edge_removed(self):
        timeline = InfraTimeline()
        g1 = _make_graph_with_components(
            _make_component("a", "A"),
            _make_component("b", "B"),
        )
        g1.add_dependency(Dependency(source_id="a", target_id="b", dependency_type="requires"))

        g2 = _make_graph_with_components(
            _make_component("a", "A"),
            _make_component("b", "B"),
        )

        changes = timeline.diff_graphs(g1, g2)
        edge_removed = [c for c in changes if c.change_type == ChangeType.EDGE_REMOVED]
        assert len(edge_removed) == 1

    def test_no_changes_between_identical_graphs(self):
        timeline = InfraTimeline()
        g1 = _basic_graph()
        g2 = _basic_graph()

        changes = timeline.diff_graphs(g1, g2)
        assert len(changes) == 0

    def test_capacity_change_detected(self):
        timeline = InfraTimeline()
        comp1 = _make_component("api", "API")
        comp1.capacity.max_connections = 1000
        g1 = _make_graph_with_components(comp1)

        comp2 = _make_component("api", "API")
        comp2.capacity.max_connections = 5000
        g2 = _make_graph_with_components(comp2)

        changes = timeline.diff_graphs(g1, g2)
        cap_changes = [c for c in changes if c.change_type == ChangeType.CAPACITY_CHANGED]
        assert len(cap_changes) == 1
        assert cap_changes[0].field == "capacity.max_connections"

    def test_config_change_detected_for_metrics(self):
        timeline = InfraTimeline()
        comp1 = _make_component("api", "API")
        comp1.metrics.cpu_percent = 20.0
        g1 = _make_graph_with_components(comp1)

        comp2 = _make_component("api", "API")
        comp2.metrics.cpu_percent = 80.0
        g2 = _make_graph_with_components(comp2)

        changes = timeline.diff_graphs(g1, g2)
        config_changes = [c for c in changes if c.change_type == ChangeType.CONFIG_CHANGED]
        assert len(config_changes) >= 1
        cpu_change = [c for c in config_changes if c.field == "metrics.cpu_percent"]
        assert len(cpu_change) == 1


# ===========================================================================
# Test: Log and search
# ===========================================================================

class TestLogAndSearch:
    def test_log_returns_recent_entries(self):
        timeline = InfraTimeline()
        g = _basic_graph()
        timeline.snapshot(g, "admin", "first")
        timeline.snapshot(g, "admin", "second")
        timeline.snapshot(g, "admin", "third")

        entries = timeline.log(limit=2)
        assert len(entries) == 2
        # Most recent first
        assert entries[0].commit.message == "third"
        assert entries[1].commit.message == "second"

    def test_log_all_entries(self):
        timeline = InfraTimeline()
        g = _basic_graph()
        for i in range(5):
            timeline.snapshot(g, "admin", f"commit-{i}")

        entries = timeline.log(limit=20)
        assert len(entries) == 5

    def test_log_empty_timeline(self):
        timeline = InfraTimeline()
        entries = timeline.log()
        assert entries == []

    def test_search_by_message(self):
        timeline = InfraTimeline()
        g = _basic_graph()
        timeline.snapshot(g, "admin", "initial setup")
        timeline.snapshot(g, "admin", "scale database")
        timeline.snapshot(g, "admin", "add cache layer")

        results = timeline.search("database")
        assert len(results) == 1
        assert results[0].message == "scale database"

    def test_search_case_insensitive(self):
        timeline = InfraTimeline()
        g = _basic_graph()
        timeline.snapshot(g, "admin", "Scale Database")

        results = timeline.search("scale database")
        assert len(results) == 1

    def test_search_no_match(self):
        timeline = InfraTimeline()
        g = _basic_graph()
        timeline.snapshot(g, "admin", "initial")

        results = timeline.search("nonexistent")
        assert results == []

    def test_search_multiple_matches(self):
        timeline = InfraTimeline()
        g = _basic_graph()
        timeline.snapshot(g, "admin", "deploy v1")
        timeline.snapshot(g, "admin", "deploy v2")
        timeline.snapshot(g, "admin", "rollback v1")

        results = timeline.search("deploy")
        assert len(results) == 2


# ===========================================================================
# Test: Tagging
# ===========================================================================

class TestTagging:
    def test_add_tag(self):
        timeline = InfraTimeline()
        g = _basic_graph()
        commit = timeline.snapshot(g, "admin", "release")

        timeline.tag(commit.commit_id, "v1.0")
        retrieved = timeline.get_commit(commit.commit_id)
        assert "v1.0" in retrieved.tags

    def test_add_multiple_tags(self):
        timeline = InfraTimeline()
        g = _basic_graph()
        commit = timeline.snapshot(g, "admin", "release")

        timeline.tag(commit.commit_id, "v1.0")
        timeline.tag(commit.commit_id, "production")
        retrieved = timeline.get_commit(commit.commit_id)
        assert "v1.0" in retrieved.tags
        assert "production" in retrieved.tags

    def test_duplicate_tag_not_added(self):
        timeline = InfraTimeline()
        g = _basic_graph()
        commit = timeline.snapshot(g, "admin", "release")

        timeline.tag(commit.commit_id, "v1.0")
        timeline.tag(commit.commit_id, "v1.0")  # duplicate
        retrieved = timeline.get_commit(commit.commit_id)
        assert retrieved.tags.count("v1.0") == 1

    def test_tag_nonexistent_commit_raises(self):
        timeline = InfraTimeline()
        with pytest.raises(KeyError):
            timeline.tag("nonexistent", "v1.0")

    def test_snapshot_with_tags(self):
        timeline = InfraTimeline()
        g = _basic_graph()
        commit = timeline.snapshot(g, "admin", "release", tags=["v1.0", "stable"])

        assert "v1.0" in commit.tags
        assert "stable" in commit.tags


# ===========================================================================
# Test: get_commit
# ===========================================================================

class TestGetCommit:
    def test_get_existing_commit(self):
        timeline = InfraTimeline()
        g = _basic_graph()
        commit = timeline.snapshot(g, "admin", "initial")

        retrieved = timeline.get_commit(commit.commit_id)
        assert retrieved.commit_id == commit.commit_id
        assert retrieved.message == "initial"

    def test_get_nonexistent_commit_raises(self):
        timeline = InfraTimeline()
        with pytest.raises(KeyError):
            timeline.get_commit("nonexistent")


# ===========================================================================
# Test: Blame
# ===========================================================================

class TestBlame:
    def test_blame_shows_all_changes_to_component(self):
        timeline = InfraTimeline()

        g1 = _basic_graph()
        timeline.snapshot(g1, "admin", "initial")

        g2 = _basic_graph()
        # Modify db replicas
        db = g2.get_component("db")
        assert db is not None
        # Need to create new graph since components are immutable
        g2_mod = InfraGraph()
        g2_mod.add_component(_make_component("lb", "Load Balancer", ComponentType.LOAD_BALANCER, replicas=2))
        g2_mod.add_component(_make_component("api", "API Server", ComponentType.APP_SERVER, replicas=2))
        g2_mod.add_component(_make_component("db", "Database", ComponentType.DATABASE, replicas=3))
        g2_mod.add_dependency(Dependency(source_id="lb", target_id="api", dependency_type="requires"))
        g2_mod.add_dependency(Dependency(source_id="api", target_id="db", dependency_type="requires"))
        timeline.snapshot(g2_mod, "admin", "scale db")

        blame_changes = timeline.blame("db")
        assert len(blame_changes) >= 2  # added initially + replicas changed

    def test_blame_empty_for_nonexistent_component(self):
        timeline = InfraTimeline()
        g = _basic_graph()
        timeline.snapshot(g, "admin", "initial")

        blame_changes = timeline.blame("nonexistent")
        assert blame_changes == []

    def test_blame_tracks_multiple_modifications(self):
        timeline = InfraTimeline()

        g1 = _make_graph_with_components(_make_component("api", "API", replicas=1))
        timeline.snapshot(g1, "admin", "initial")

        g2 = _make_graph_with_components(_make_component("api", "API", replicas=2))
        timeline.snapshot(g2, "admin", "scale up")

        g3 = _make_graph_with_components(_make_component("api", "API", replicas=4))
        timeline.snapshot(g3, "admin", "scale up more")

        blame_changes = timeline.blame("api")
        # Initial add + 2 replica changes
        assert len(blame_changes) == 3


# ===========================================================================
# Test: Changelog generation
# ===========================================================================

class TestChangelog:
    def test_changelog_contains_commit_ids(self):
        timeline = InfraTimeline()
        g = _basic_graph()
        c1 = timeline.snapshot(g, "admin", "initial")

        changelog = timeline.changelog()
        assert c1.commit_id in changelog

    def test_changelog_contains_sections(self):
        timeline = InfraTimeline()
        g1 = _basic_graph()
        timeline.snapshot(g1, "admin", "initial setup")

        g2 = _modified_graph()
        timeline.snapshot(g2, "admin", "restructure")

        changelog = timeline.changelog()
        assert "# Changelog" in changelog
        # Should contain Added/Changed/Removed sections
        assert "### Added" in changelog or "### Changed" in changelog or "### Removed" in changelog

    def test_changelog_contains_resilience_impact(self):
        timeline = InfraTimeline()
        g1 = _basic_graph()
        timeline.snapshot(g1, "admin", "v1")

        g2 = _modified_graph()
        timeline.snapshot(g2, "admin", "v2")

        changelog = timeline.changelog()
        assert "Resilience" in changelog

    def test_changelog_with_tags(self):
        timeline = InfraTimeline()
        g = _basic_graph()
        c = timeline.snapshot(g, "admin", "release", tags=["v1.0"])

        changelog = timeline.changelog()
        assert "v1.0" in changelog

    def test_changelog_range_from_to(self):
        timeline = InfraTimeline()
        g = _basic_graph()
        c1 = timeline.snapshot(g, "admin", "first")
        c2 = timeline.snapshot(g, "admin", "second")
        c3 = timeline.snapshot(g, "admin", "third")

        # Only include c2 and c3 (from c1 exclusive to c3 inclusive)
        changelog = timeline.changelog(from_id=c1.commit_id, to_id=c3.commit_id)
        assert "second" in changelog
        assert "third" in changelog
        # c1 should NOT be included (from_id is exclusive)
        assert "first" not in changelog.split("# Changelog")[1]

    def test_changelog_empty_timeline(self):
        timeline = InfraTimeline()
        changelog = timeline.changelog()
        assert "No entries" in changelog

    def test_changelog_empty_range(self):
        timeline = InfraTimeline()
        g = _basic_graph()
        c1 = timeline.snapshot(g, "admin", "first")
        c2 = timeline.snapshot(g, "admin", "second")

        # From c2 to c1 is an empty range (start > end)
        changelog = timeline.changelog(from_id=c2.commit_id, to_id=c1.commit_id)
        assert "No entries in range" in changelog

    def test_changelog_shows_added_components(self):
        timeline = InfraTimeline()
        g1 = InfraGraph()
        timeline.snapshot(g1, "admin", "empty start")

        g2 = _make_graph_with_components(
            _make_component("cache", "Redis Cache", ComponentType.CACHE, replicas=3),
        )
        timeline.snapshot(g2, "admin", "add cache")

        changelog = timeline.changelog()
        assert "Redis Cache" in changelog
        assert "Added" in changelog

    def test_changelog_shows_removed_components(self):
        timeline = InfraTimeline()
        g1 = _basic_graph()
        timeline.snapshot(g1, "admin", "initial")

        g2 = _make_graph_with_components(
            _make_component("api", "API Server", ComponentType.APP_SERVER, replicas=2),
        )
        timeline.snapshot(g2, "admin", "remove lb and db")

        changelog = timeline.changelog()
        assert "Removed" in changelog


# ===========================================================================
# Test: Sparkline generation
# ===========================================================================

class TestSparkline:
    def test_sparkline_basic(self):
        timeline = InfraTimeline()
        # Create entries with varying scores by adding/removing components
        for i in range(5):
            g = InfraGraph()
            for j in range(i + 1):
                g.add_component(
                    _make_component(f"c{j}", f"C{j}", replicas=2)
                )
            timeline.snapshot(g, "admin", f"step-{i}")

        sparkline = timeline.get_timeline_sparkline("component_count")
        assert len(sparkline) > 0
        assert len(sparkline) <= 40

    def test_sparkline_single_entry(self):
        timeline = InfraTimeline()
        g = _basic_graph()
        timeline.snapshot(g, "admin", "initial")

        sparkline = timeline.get_timeline_sparkline()
        assert len(sparkline) == 1

    def test_sparkline_empty_timeline(self):
        timeline = InfraTimeline()
        sparkline = timeline.get_timeline_sparkline()
        assert sparkline == ""

    def test_sparkline_constant_values(self):
        timeline = InfraTimeline()
        g = _basic_graph()
        for i in range(10):
            timeline.snapshot(g, "admin", f"step-{i}")

        sparkline = timeline.get_timeline_sparkline("component_count")
        # All same value => all same char
        assert len(set(sparkline)) == 1

    def test_sparkline_width_limit(self):
        timeline = InfraTimeline()
        for i in range(100):
            g = _make_graph_with_components(
                _make_component(f"c{i}", f"C{i}", replicas=i % 5 + 1)
            )
            timeline.snapshot(g, "admin", f"step-{i}")

        sparkline = timeline.get_timeline_sparkline(width=20)
        assert len(sparkline) <= 20

    def test_sparkline_edge_count(self):
        timeline = InfraTimeline()
        g = _basic_graph()
        timeline.snapshot(g, "admin", "initial")

        sparkline = timeline.get_timeline_sparkline("edge_count")
        assert len(sparkline) == 1

    def test_sparkline_unknown_field(self):
        timeline = InfraTimeline()
        g = _basic_graph()
        timeline.snapshot(g, "admin", "initial")

        sparkline = timeline.get_timeline_sparkline("unknown_field")
        # Should not raise, returns sparkline of 0 values
        assert len(sparkline) == 1

    def test_sparkline_uses_block_chars(self):
        timeline = InfraTimeline()
        block_chars = "\u2581\u2582\u2583\u2584\u2585\u2586\u2587\u2588"

        for i in range(8):
            g = InfraGraph()
            for j in range(i + 1):
                g.add_component(_make_component(f"c{i}_{j}", f"C{i}_{j}", replicas=2))
            timeline.snapshot(g, "admin", f"step-{i}")

        sparkline = timeline.get_timeline_sparkline("component_count")
        for ch in sparkline:
            assert ch in block_chars


# ===========================================================================
# Test: Rollback
# ===========================================================================

class TestRollback:
    def test_rollback_to_previous_state(self):
        timeline = InfraTimeline()

        g1 = _basic_graph()
        c1 = timeline.snapshot(g1, "admin", "v1")

        g2 = _modified_graph()
        c2 = timeline.snapshot(g2, "admin", "v2")

        # Rollback to v1
        restored = timeline.rollback_to(c1.commit_id)
        assert "lb" in restored.components
        assert "api" in restored.components
        assert "db" in restored.components
        assert "cache" not in restored.components

    def test_rollback_to_latest(self):
        timeline = InfraTimeline()
        g1 = _basic_graph()
        c1 = timeline.snapshot(g1, "admin", "v1")

        g2 = _modified_graph()
        c2 = timeline.snapshot(g2, "admin", "v2")

        restored = timeline.rollback_to(c2.commit_id)
        assert "cache" in restored.components
        assert "lb" not in restored.components

    def test_rollback_preserves_edges(self):
        timeline = InfraTimeline()
        g = _basic_graph()
        c = timeline.snapshot(g, "admin", "with edges")

        restored = timeline.rollback_to(c.commit_id)
        edges = restored.all_dependency_edges()
        assert len(edges) == 2

    def test_rollback_nonexistent_commit_raises(self):
        timeline = InfraTimeline()
        with pytest.raises(KeyError):
            timeline.rollback_to("nonexistent")

    def test_rollback_graph_is_independent_copy(self):
        timeline = InfraTimeline()
        g = _basic_graph()
        c = timeline.snapshot(g, "admin", "original")

        restored = timeline.rollback_to(c.commit_id)
        # Modifying restored should not affect stored snapshot
        restored.add_component(_make_component("new", "New"))
        assert "new" in restored.components

        restored2 = timeline.rollback_to(c.commit_id)
        assert "new" not in restored2.components


# ===========================================================================
# Test: Persistence (save/load from JSONL)
# ===========================================================================

class TestPersistence:
    def test_save_and_load(self, tmp_path: Path):
        storage = tmp_path / "timeline.jsonl"

        # Create and populate timeline
        tl1 = InfraTimeline(storage_path=storage)
        g1 = _basic_graph()
        c1 = tl1.snapshot(g1, "admin", "initial", tags=["v1.0"])

        g2 = _modified_graph()
        c2 = tl1.snapshot(g2, "admin", "update")

        assert storage.exists()

        # Load from file in new instance
        tl2 = InfraTimeline(storage_path=storage)
        entries = tl2.log()
        assert len(entries) == 2
        assert entries[0].commit.message == "update"
        assert entries[1].commit.message == "initial"

    def test_persisted_tags_survive_reload(self, tmp_path: Path):
        storage = tmp_path / "timeline.jsonl"

        tl1 = InfraTimeline(storage_path=storage)
        g = _basic_graph()
        c = tl1.snapshot(g, "admin", "release", tags=["v1.0"])
        tl1.tag(c.commit_id, "production")

        tl2 = InfraTimeline(storage_path=storage)
        commit = tl2.get_commit(c.commit_id)
        assert "v1.0" in commit.tags
        assert "production" in commit.tags

    def test_persisted_snapshots_allow_rollback(self, tmp_path: Path):
        storage = tmp_path / "timeline.jsonl"

        tl1 = InfraTimeline(storage_path=storage)
        g = _basic_graph()
        c = tl1.snapshot(g, "admin", "initial")

        tl2 = InfraTimeline(storage_path=storage)
        restored = tl2.rollback_to(c.commit_id)
        assert len(restored.components) == 3

    def test_persisted_diff_works(self, tmp_path: Path):
        storage = tmp_path / "timeline.jsonl"

        tl1 = InfraTimeline(storage_path=storage)
        g1 = _basic_graph()
        c1 = tl1.snapshot(g1, "admin", "v1")
        g2 = _modified_graph()
        c2 = tl1.snapshot(g2, "admin", "v2")

        tl2 = InfraTimeline(storage_path=storage)
        diff = tl2.diff(c1.commit_id, c2.commit_id)
        assert diff.components_added >= 1

    def test_no_storage_path_no_file_created(self, tmp_path: Path):
        tl = InfraTimeline(storage_path=None)
        g = _basic_graph()
        tl.snapshot(g, "admin", "test")
        # No file should be created in tmp_path
        assert list(tmp_path.iterdir()) == []

    def test_load_empty_file(self, tmp_path: Path):
        storage = tmp_path / "timeline.jsonl"
        storage.write_text("")

        tl = InfraTimeline(storage_path=storage)
        assert tl.log() == []

    def test_load_corrupt_file(self, tmp_path: Path):
        storage = tmp_path / "timeline.jsonl"
        storage.write_text("this is not valid json")

        tl = InfraTimeline(storage_path=storage)
        assert tl.log() == []

    def test_storage_creates_parent_directories(self, tmp_path: Path):
        storage = tmp_path / "deep" / "nested" / "dir" / "timeline.jsonl"

        tl = InfraTimeline(storage_path=storage)
        g = _basic_graph()
        tl.snapshot(g, "admin", "test")

        assert storage.exists()


# ===========================================================================
# Test: Edge cases
# ===========================================================================

class TestEdgeCases:
    def test_empty_graph_snapshot(self):
        timeline = InfraTimeline()
        g = InfraGraph()
        commit = timeline.snapshot(g, "admin", "empty")

        assert len(commit.changes) == 0
        assert commit.parent_id is None

    def test_graph_with_no_edges(self):
        timeline = InfraTimeline()
        g = _make_graph_with_components(
            _make_component("a", "A"),
            _make_component("b", "B"),
        )
        commit = timeline.snapshot(g, "admin", "no edges")

        added = [c for c in commit.changes if c.change_type == ChangeType.COMPONENT_ADDED]
        edges = [c for c in commit.changes if c.change_type == ChangeType.EDGE_ADDED]
        assert len(added) == 2
        assert len(edges) == 0

    def test_first_commit_has_no_parent(self):
        timeline = InfraTimeline()
        g = _basic_graph()
        commit = timeline.snapshot(g, "admin", "first")
        assert commit.parent_id is None

    def test_second_commit_has_parent(self):
        timeline = InfraTimeline()
        g = _basic_graph()
        c1 = timeline.snapshot(g, "admin", "first")
        c2 = timeline.snapshot(g, "admin", "second")
        assert c2.parent_id == c1.commit_id

    def test_many_snapshots_performance(self):
        """Ensure many snapshots don't cause issues."""
        timeline = InfraTimeline()
        g = _basic_graph()
        for i in range(50):
            timeline.snapshot(g, "admin", f"snapshot-{i}")

        entries = timeline.log(limit=50)
        assert len(entries) == 50

    def test_component_with_all_tracked_changes(self):
        """Test a component changing multiple tracked fields at once."""
        timeline = InfraTimeline()
        g1 = _make_graph_with_components(
            _make_component("api", "API", replicas=1, failover=False, autoscaling=False),
        )
        timeline.snapshot(g1, "admin", "v1")

        g2 = _make_graph_with_components(
            _make_component("api", "API", replicas=3, failover=True, autoscaling=True),
        )
        c2 = timeline.snapshot(g2, "admin", "v2")

        change_types = {c.change_type for c in c2.changes}
        assert ChangeType.REPLICAS_CHANGED in change_types
        assert ChangeType.FAILOVER_TOGGLED in change_types
        assert ChangeType.AUTOSCALING_TOGGLED in change_types


# ===========================================================================
# Test: Commit ID generation
# ===========================================================================

class TestCommitIdGeneration:
    def test_commit_id_is_8_chars(self):
        cid = _generate_commit_id("2024-01-01T00:00:00Z", [])
        assert len(cid) == 8

    def test_commit_id_is_hex(self):
        cid = _generate_commit_id("2024-01-01T00:00:00Z", [])
        assert all(c in "0123456789abcdef" for c in cid)

    def test_different_timestamps_produce_different_ids(self):
        id1 = _generate_commit_id("2024-01-01T00:00:00Z", [])
        id2 = _generate_commit_id("2024-01-01T00:00:01Z", [])
        assert id1 != id2

    def test_different_changes_produce_different_ids(self):
        ch1 = InfraChange(
            change_type=ChangeType.COMPONENT_ADDED,
            component_id="a", component_name="A",
            field=None, old_value=None, new_value="added",
            timestamp="t", author="a", message="m",
        )
        ch2 = InfraChange(
            change_type=ChangeType.COMPONENT_REMOVED,
            component_id="b", component_name="B",
            field=None, old_value="removed", new_value=None,
            timestamp="t", author="a", message="m",
        )
        id1 = _generate_commit_id("same-ts", [ch1])
        id2 = _generate_commit_id("same-ts", [ch2])
        assert id1 != id2

    def test_same_input_produces_same_id(self):
        ch = InfraChange(
            change_type=ChangeType.COMPONENT_ADDED,
            component_id="a", component_name="A",
            field=None, old_value=None, new_value="added",
            timestamp="t", author="a", message="m",
        )
        id1 = _generate_commit_id("ts", [ch])
        id2 = _generate_commit_id("ts", [ch])
        assert id1 == id2


# ===========================================================================
# Test: Serialization helpers
# ===========================================================================

class TestSerialization:
    def test_change_roundtrip(self):
        ch = InfraChange(
            change_type=ChangeType.REPLICAS_CHANGED,
            component_id="api",
            component_name="API Server",
            field="replicas",
            old_value="1",
            new_value="3",
            timestamp="2024-01-15T00:00:00Z",
            author="admin",
            message="scale up",
        )
        d = _change_to_dict(ch)
        restored = _change_from_dict(d)
        assert restored.change_type == ch.change_type
        assert restored.component_id == ch.component_id
        assert restored.old_value == ch.old_value
        assert restored.new_value == ch.new_value

    def test_commit_roundtrip(self):
        ch = InfraChange(
            change_type=ChangeType.COMPONENT_ADDED,
            component_id="x", component_name="X",
            field=None, old_value=None, new_value="added",
            timestamp="t", author="a", message="m",
        )
        commit = InfraCommit(
            commit_id="abcd1234",
            changes=[ch],
            timestamp="2024-01-15T00:00:00Z",
            author="admin",
            message="initial",
            parent_id=None,
            tags=["v1.0"],
            snapshot_hash="hash123",
        )
        d = _commit_to_dict(commit)
        restored = _commit_from_dict(d)
        assert restored.commit_id == commit.commit_id
        assert len(restored.changes) == 1
        assert restored.tags == ["v1.0"]
        assert restored.parent_id is None

    def test_entry_roundtrip(self):
        commit = InfraCommit(
            commit_id="x", changes=[], timestamp="t", author="a",
            message="m", parent_id=None, tags=[], snapshot_hash="h",
        )
        entry = TimelineEntry(
            commit=commit, resilience_score=85.5,
            component_count=5, edge_count=4,
        )
        d = _entry_to_dict(entry)
        restored = _entry_from_dict(d)
        assert restored.resilience_score == 85.5
        assert restored.component_count == 5
        assert restored.edge_count == 4
        assert restored.commit.commit_id == "x"


# ===========================================================================
# Test: Graph hash
# ===========================================================================

class TestGraphHash:
    def test_hash_deterministic(self):
        g1 = _basic_graph()
        g2 = _basic_graph()
        assert _graph_hash(g1) == _graph_hash(g2)

    def test_hash_differs_for_different_graphs(self):
        g1 = _basic_graph()
        g2 = _modified_graph()
        assert _graph_hash(g1) != _graph_hash(g2)

    def test_empty_graph_hash(self):
        g = InfraGraph()
        h = _graph_hash(g)
        assert len(h) == 64  # sha256 hex length

    def test_hash_changes_with_replicas(self):
        g1 = _make_graph_with_components(_make_component("a", "A", replicas=1))
        g2 = _make_graph_with_components(_make_component("a", "A", replicas=3))
        assert _graph_hash(g1) != _graph_hash(g2)


# ===========================================================================
# Test: _get_component_field helper
# ===========================================================================

class TestGetComponentField:
    def test_get_nested_field(self):
        comp = _make_component("api", "API")
        comp.capacity.max_connections = 5000
        val = _get_component_field(comp, ("capacity", "max_connections"))
        assert val == 5000

    def test_get_nonexistent_field(self):
        comp = _make_component("api", "API")
        val = _get_component_field(comp, ("nonexistent", "field"))
        assert val is None

    def test_get_single_level_field(self):
        comp = _make_component("api", "API", replicas=3)
        val = _get_component_field(comp, ("replicas",))
        assert val == 3
