"""Tests for topology comparator."""

from __future__ import annotations

import pytest

from faultray.model.components import Component, ComponentType, Dependency, HealthStatus
from faultray.model.graph import InfraGraph
from faultray.simulator.topology_comparator import (
    ChangeImpact,
    ChangeType,
    TopologyChange,
    TopologyComparator,
    TopologyDiff,
    TopologyMetrics,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _comp(
    cid: str,
    name: str,
    ctype: ComponentType = ComponentType.APP_SERVER,
    replicas: int = 1,
    failover: bool = False,
    health: HealthStatus = HealthStatus.HEALTHY,
) -> Component:
    c = Component(id=cid, name=name, type=ctype, replicas=replicas)
    c.health = health
    if failover:
        c.failover.enabled = True
    return c


def _simple_graph() -> InfraGraph:
    g = InfraGraph()
    g.add_component(_comp("lb", "Load Balancer", ComponentType.LOAD_BALANCER, replicas=2))
    g.add_component(_comp("api", "API Server", replicas=2))
    g.add_component(_comp("db", "Database", ComponentType.DATABASE, replicas=3))
    g.add_dependency(Dependency(source_id="lb", target_id="api"))
    g.add_dependency(Dependency(source_id="api", target_id="db"))
    return g


# ---------------------------------------------------------------------------
# Tests: Enums
# ---------------------------------------------------------------------------


class TestEnums:
    def test_change_type_values(self):
        assert ChangeType.COMPONENT_ADDED.value == "component_added"
        assert ChangeType.DEPENDENCY_REMOVED.value == "dependency_removed"

    def test_change_impact_values(self):
        assert ChangeImpact.BREAKING.value == "breaking"
        assert ChangeImpact.COSMETIC.value == "cosmetic"


# ---------------------------------------------------------------------------
# Tests: Identical graphs
# ---------------------------------------------------------------------------


class TestIdenticalGraphs:
    def test_same_graph(self):
        comp = TopologyComparator()
        g = _simple_graph()
        diff = comp.compare(g, g)
        assert diff.total_changes == 0
        assert diff.similarity_score == 100.0
        assert diff.breaking_changes == 0

    def test_identical_summary(self):
        comp = TopologyComparator()
        g = _simple_graph()
        diff = comp.compare(g, g)
        assert "identical" in diff.summary.lower()

    def test_empty_graphs(self):
        comp = TopologyComparator()
        g1 = InfraGraph()
        g2 = InfraGraph()
        diff = comp.compare(g1, g2)
        assert diff.total_changes == 0
        assert diff.similarity_score == 100.0


# ---------------------------------------------------------------------------
# Tests: Component additions
# ---------------------------------------------------------------------------


class TestComponentAdditions:
    def test_added_component(self):
        comp = TopologyComparator()
        g1 = InfraGraph()
        g1.add_component(_comp("api", "API"))

        g2 = InfraGraph()
        g2.add_component(_comp("api", "API"))
        g2.add_component(_comp("cache", "Cache", ComponentType.CACHE))

        diff = comp.compare(g1, g2)
        assert "cache" in diff.added_components
        assert len(diff.added_components) == 1

    def test_added_component_change_type(self):
        comp = TopologyComparator()
        g1 = InfraGraph()
        g2 = InfraGraph()
        g2.add_component(_comp("api", "API"))

        diff = comp.compare(g1, g2)
        adds = [c for c in diff.changes if c.change_type == ChangeType.COMPONENT_ADDED]
        assert len(adds) == 1
        assert adds[0].component_id == "api"

    def test_added_with_dependents_significant(self):
        comp = TopologyComparator()
        g1 = InfraGraph()
        g1.add_component(_comp("api", "API"))

        g2 = InfraGraph()
        g2.add_component(_comp("api", "API"))
        g2.add_component(_comp("db", "DB", ComponentType.DATABASE))
        g2.add_dependency(Dependency(source_id="api", target_id="db"))

        diff = comp.compare(g1, g2)
        db_changes = [c for c in diff.changes if c.component_id == "db"]
        # DB has a dependent (api), so impact is SIGNIFICANT
        assert any(c.impact == ChangeImpact.SIGNIFICANT for c in db_changes)


# ---------------------------------------------------------------------------
# Tests: Component removals
# ---------------------------------------------------------------------------


class TestComponentRemovals:
    def test_removed_component(self):
        comp = TopologyComparator()
        g1 = InfraGraph()
        g1.add_component(_comp("api", "API"))
        g1.add_component(_comp("cache", "Cache", ComponentType.CACHE))

        g2 = InfraGraph()
        g2.add_component(_comp("api", "API"))

        diff = comp.compare(g1, g2)
        assert "cache" in diff.removed_components

    def test_removed_with_dependents_breaking(self):
        comp = TopologyComparator()
        g1 = _simple_graph()  # lb -> api -> db

        g2 = InfraGraph()
        g2.add_component(_comp("lb", "Load Balancer", ComponentType.LOAD_BALANCER))
        # api removed (lb depends on it)

        diff = comp.compare(g1, g2)
        api_removes = [
            c for c in diff.changes
            if c.component_id == "api" and c.change_type == ChangeType.COMPONENT_REMOVED
        ]
        assert len(api_removes) == 1
        assert api_removes[0].impact == ChangeImpact.BREAKING

    def test_removed_isolated_significant(self):
        comp = TopologyComparator()
        g1 = InfraGraph()
        g1.add_component(_comp("a", "A"))
        g1.add_component(_comp("b", "B"))

        g2 = InfraGraph()
        g2.add_component(_comp("a", "A"))

        diff = comp.compare(g1, g2)
        b_changes = [c for c in diff.changes if c.component_id == "b"]
        assert b_changes[0].impact == ChangeImpact.SIGNIFICANT


# ---------------------------------------------------------------------------
# Tests: Component modifications
# ---------------------------------------------------------------------------


class TestComponentModifications:
    def test_replica_change(self):
        comp = TopologyComparator()
        g1 = InfraGraph()
        g1.add_component(_comp("api", "API", replicas=3))

        g2 = InfraGraph()
        g2.add_component(_comp("api", "API", replicas=1))

        diff = comp.compare(g1, g2)
        assert "api" in diff.modified_components
        mods = [c for c in diff.changes if c.change_type == ChangeType.COMPONENT_MODIFIED]
        assert any("Replicas" in c.description for c in mods)

    def test_replica_decrease_significant(self):
        comp = TopologyComparator()
        g1 = InfraGraph()
        g1.add_component(_comp("api", "API", replicas=3))
        g2 = InfraGraph()
        g2.add_component(_comp("api", "API", replicas=1))

        diff = comp.compare(g1, g2)
        mods = [c for c in diff.changes if "Replicas" in c.description]
        assert mods[0].impact == ChangeImpact.SIGNIFICANT

    def test_replica_increase_minor(self):
        comp = TopologyComparator()
        g1 = InfraGraph()
        g1.add_component(_comp("api", "API", replicas=1))
        g2 = InfraGraph()
        g2.add_component(_comp("api", "API", replicas=3))

        diff = comp.compare(g1, g2)
        mods = [c for c in diff.changes if "Replicas" in c.description]
        assert mods[0].impact == ChangeImpact.MINOR

    def test_type_change_breaking(self):
        comp = TopologyComparator()
        g1 = InfraGraph()
        g1.add_component(_comp("x", "X", ComponentType.APP_SERVER))
        g2 = InfraGraph()
        g2.add_component(_comp("x", "X", ComponentType.DATABASE))

        diff = comp.compare(g1, g2)
        type_changes = [c for c in diff.changes if "Type" in c.description]
        assert type_changes[0].impact == ChangeImpact.BREAKING

    def test_failover_disabled_significant(self):
        comp = TopologyComparator()
        g1 = InfraGraph()
        g1.add_component(_comp("db", "DB", failover=True))
        g2 = InfraGraph()
        g2.add_component(_comp("db", "DB", failover=False))

        diff = comp.compare(g1, g2)
        fo_changes = [c for c in diff.changes if "Failover" in c.description]
        assert fo_changes[0].impact == ChangeImpact.SIGNIFICANT

    def test_failover_enabled_minor(self):
        comp = TopologyComparator()
        g1 = InfraGraph()
        g1.add_component(_comp("db", "DB", failover=False))
        g2 = InfraGraph()
        g2.add_component(_comp("db", "DB", failover=True))

        diff = comp.compare(g1, g2)
        fo_changes = [c for c in diff.changes if "Failover" in c.description]
        assert fo_changes[0].impact == ChangeImpact.MINOR

    def test_health_change_down_significant(self):
        comp = TopologyComparator()
        g1 = InfraGraph()
        g1.add_component(_comp("api", "API", health=HealthStatus.HEALTHY))
        g2 = InfraGraph()
        g2.add_component(_comp("api", "API", health=HealthStatus.DOWN))

        diff = comp.compare(g1, g2)
        health_changes = [c for c in diff.changes if "Health" in c.description]
        assert health_changes[0].impact == ChangeImpact.SIGNIFICANT

    def test_no_modifications_when_same(self):
        comp = TopologyComparator()
        g1 = InfraGraph()
        g1.add_component(_comp("api", "API", replicas=2))
        g2 = InfraGraph()
        g2.add_component(_comp("api", "API", replicas=2))

        diff = comp.compare(g1, g2)
        assert len(diff.modified_components) == 0


# ---------------------------------------------------------------------------
# Tests: Dependency changes
# ---------------------------------------------------------------------------


class TestDependencyChanges:
    def test_added_dependency(self):
        comp = TopologyComparator()
        g1 = InfraGraph()
        g1.add_component(_comp("api", "API"))
        g1.add_component(_comp("db", "DB"))

        g2 = InfraGraph()
        g2.add_component(_comp("api", "API"))
        g2.add_component(_comp("db", "DB"))
        g2.add_dependency(Dependency(source_id="api", target_id="db"))

        diff = comp.compare(g1, g2)
        assert ("api", "db") in diff.added_dependencies

    def test_removed_dependency(self):
        comp = TopologyComparator()
        g1 = InfraGraph()
        g1.add_component(_comp("api", "API"))
        g1.add_component(_comp("db", "DB"))
        g1.add_dependency(Dependency(source_id="api", target_id="db"))

        g2 = InfraGraph()
        g2.add_component(_comp("api", "API"))
        g2.add_component(_comp("db", "DB"))

        diff = comp.compare(g1, g2)
        assert ("api", "db") in diff.removed_dependencies


# ---------------------------------------------------------------------------
# Tests: Topology metrics
# ---------------------------------------------------------------------------


class TestTopologyMetrics:
    def test_before_metrics(self):
        comp = TopologyComparator()
        g1 = _simple_graph()
        g2 = InfraGraph()

        diff = comp.compare(g1, g2)
        assert diff.before_metrics.component_count == 3
        assert diff.before_metrics.dependency_count == 2

    def test_after_metrics(self):
        comp = TopologyComparator()
        g1 = InfraGraph()
        g2 = _simple_graph()

        diff = comp.compare(g1, g2)
        assert diff.after_metrics.component_count == 3

    def test_empty_metrics(self):
        comp = TopologyComparator()
        g = InfraGraph()
        diff = comp.compare(g, g)
        assert diff.before_metrics.component_count == 0
        assert diff.before_metrics.resilience_score == 100.0

    def test_spof_count(self):
        comp = TopologyComparator()
        g = InfraGraph()
        g.add_component(_comp("api", "API", replicas=1))
        g.add_component(_comp("db", "DB", replicas=1))
        g.add_dependency(Dependency(source_id="api", target_id="db"))

        diff = comp.compare(g, g)
        # db has 1 replica and dependents (api)
        assert diff.before_metrics.spof_count >= 1

    def test_isolated_count(self):
        comp = TopologyComparator()
        g = InfraGraph()
        g.add_component(_comp("a", "A"))
        g.add_component(_comp("b", "B"))

        diff = comp.compare(g, g)
        assert diff.before_metrics.isolated_count == 2


# ---------------------------------------------------------------------------
# Tests: Similarity score
# ---------------------------------------------------------------------------


class TestSimilarity:
    def test_identical_100(self):
        comp = TopologyComparator()
        g = _simple_graph()
        diff = comp.compare(g, g)
        assert diff.similarity_score == 100.0

    def test_completely_different(self):
        comp = TopologyComparator()
        g1 = InfraGraph()
        g1.add_component(_comp("a", "A"))

        g2 = InfraGraph()
        g2.add_component(_comp("b", "B"))

        diff = comp.compare(g1, g2)
        assert diff.similarity_score < 50.0

    def test_partial_overlap(self):
        comp = TopologyComparator()
        g1 = InfraGraph()
        g1.add_component(_comp("a", "A"))
        g1.add_component(_comp("b", "B"))

        g2 = InfraGraph()
        g2.add_component(_comp("a", "A"))
        g2.add_component(_comp("c", "C"))

        diff = comp.compare(g1, g2)
        assert 0 < diff.similarity_score < 100.0


# ---------------------------------------------------------------------------
# Tests: is_compatible
# ---------------------------------------------------------------------------


class TestCompatibility:
    def test_compatible_addition(self):
        comp = TopologyComparator()
        g1 = InfraGraph()
        g1.add_component(_comp("api", "API"))

        g2 = InfraGraph()
        g2.add_component(_comp("api", "API"))
        g2.add_component(_comp("cache", "Cache", ComponentType.CACHE))

        assert comp.is_compatible(g1, g2) is True

    def test_incompatible_removal_with_dependents(self):
        comp = TopologyComparator()
        g1 = _simple_graph()  # lb -> api -> db

        g2 = InfraGraph()
        g2.add_component(_comp("lb", "Load Balancer", ComponentType.LOAD_BALANCER))
        # api removed but lb depends on it

        assert comp.is_compatible(g1, g2) is False


# ---------------------------------------------------------------------------
# Tests: Summary
# ---------------------------------------------------------------------------


class TestSummary:
    def test_summary_with_additions(self):
        comp = TopologyComparator()
        g1 = InfraGraph()
        g2 = InfraGraph()
        g2.add_component(_comp("api", "API"))

        diff = comp.compare(g1, g2)
        assert "+1 component" in diff.summary

    def test_summary_with_removals(self):
        comp = TopologyComparator()
        g1 = InfraGraph()
        g1.add_component(_comp("api", "API"))
        g2 = InfraGraph()

        diff = comp.compare(g1, g2)
        assert "-1 component" in diff.summary

    def test_summary_similarity(self):
        comp = TopologyComparator()
        g1 = InfraGraph()
        g1.add_component(_comp("api", "API"))
        g2 = InfraGraph()
        g2.add_component(_comp("api", "API"))
        g2.add_component(_comp("db", "DB"))

        diff = comp.compare(g1, g2)
        assert "Similarity:" in diff.summary


# ---------------------------------------------------------------------------
# Tests: TopologyDiff data class
# ---------------------------------------------------------------------------


class TestDiffFields:
    def test_all_fields_present(self):
        comp = TopologyComparator()
        g1 = _simple_graph()
        g2 = InfraGraph()
        g2.add_component(_comp("api", "API"))

        diff = comp.compare(g1, g2)
        assert isinstance(diff.changes, list)
        assert isinstance(diff.before_metrics, TopologyMetrics)
        assert isinstance(diff.after_metrics, TopologyMetrics)
        assert isinstance(diff.similarity_score, float)
        assert isinstance(diff.summary, str)

    def test_change_fields(self):
        comp = TopologyComparator()
        g1 = InfraGraph()
        g2 = InfraGraph()
        g2.add_component(_comp("api", "API"))

        diff = comp.compare(g1, g2)
        change = diff.changes[0]
        assert isinstance(change.change_type, ChangeType)
        assert isinstance(change.impact, ChangeImpact)
        assert isinstance(change.description, str)
