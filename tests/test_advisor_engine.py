"""Tests for the Chaos Advisor Engine."""

from __future__ import annotations

import pytest

from faultray.model.components import (
    AutoScalingConfig,
    Component,
    ComponentType,
    Dependency,
    FailoverConfig,
)
from faultray.model.graph import InfraGraph
from faultray.simulator.advisor_engine import (
    AdvisorReport,
    ChaosAdvisorEngine,
    ChaosRecommendation,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def simple_graph() -> InfraGraph:
    """Graph with a clear SPOF: single DB with multiple dependents."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="lb", name="Load Balancer", type=ComponentType.LOAD_BALANCER,
        replicas=2,
    ))
    graph.add_component(Component(
        id="app", name="App Server", type=ComponentType.APP_SERVER,
        replicas=2,
    ))
    graph.add_component(Component(
        id="db", name="PostgreSQL", type=ComponentType.DATABASE,
        replicas=1,
    ))
    graph.add_component(Component(
        id="cache", name="Redis", type=ComponentType.CACHE,
        replicas=1,
    ))
    graph.add_dependency(Dependency(source_id="lb", target_id="app", dependency_type="requires"))
    graph.add_dependency(Dependency(source_id="app", target_id="db", dependency_type="requires"))
    graph.add_dependency(Dependency(source_id="app", target_id="cache", dependency_type="optional"))
    return graph


@pytest.fixture
def redundant_graph() -> InfraGraph:
    """Graph where all components have replicas >= 2 and failover."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="lb", name="Load Balancer", type=ComponentType.LOAD_BALANCER,
        replicas=3, failover=FailoverConfig(enabled=True),
    ))
    graph.add_component(Component(
        id="app", name="App Server", type=ComponentType.APP_SERVER,
        replicas=3, failover=FailoverConfig(enabled=True),
        autoscaling=AutoScalingConfig(enabled=True),
    ))
    graph.add_component(Component(
        id="db", name="PostgreSQL", type=ComponentType.DATABASE,
        replicas=2, failover=FailoverConfig(enabled=True),
    ))
    graph.add_dependency(Dependency(source_id="lb", target_id="app", dependency_type="requires"))
    graph.add_dependency(Dependency(source_id="app", target_id="db", dependency_type="requires"))
    return graph


@pytest.fixture
def empty_graph() -> InfraGraph:
    """Completely empty graph with no components."""
    return InfraGraph()


@pytest.fixture
def single_node_graph() -> InfraGraph:
    """Graph with a single component and no dependencies."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="app", name="App", type=ComponentType.APP_SERVER, replicas=1,
    ))
    return graph


@pytest.fixture
def linear_chain_graph() -> InfraGraph:
    """Linear chain: lb -> app -> db -> storage (all single replicas)."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="lb", name="LB", type=ComponentType.LOAD_BALANCER, replicas=1,
    ))
    graph.add_component(Component(
        id="app", name="App", type=ComponentType.APP_SERVER, replicas=1,
    ))
    graph.add_component(Component(
        id="db", name="DB", type=ComponentType.DATABASE, replicas=1,
    ))
    graph.add_component(Component(
        id="storage", name="Storage", type=ComponentType.STORAGE, replicas=1,
    ))
    graph.add_dependency(Dependency(source_id="lb", target_id="app"))
    graph.add_dependency(Dependency(source_id="app", target_id="db"))
    graph.add_dependency(Dependency(source_id="db", target_id="storage"))
    return graph


# ---------------------------------------------------------------------------
# ChaosRecommendation dataclass tests
# ---------------------------------------------------------------------------


class TestChaosRecommendation:
    def test_default_values(self):
        rec = ChaosRecommendation(
            priority="critical",
            scenario_name="Test scenario",
            scenario_id="test-123",
            reasoning="Because reasons",
            risk_if_untested="Bad things happen",
            estimated_blast_radius=5,
        )
        assert rec.priority == "critical"
        assert rec.scenario_name == "Test scenario"
        assert rec.estimated_blast_radius == 5
        assert rec.target_components == []

    def test_with_targets(self):
        rec = ChaosRecommendation(
            priority="high",
            scenario_name="Pairwise failure",
            scenario_id="pair-abc",
            reasoning="Important",
            risk_if_untested="Outage",
            estimated_blast_radius=3,
            target_components=["db", "cache"],
        )
        assert rec.target_components == ["db", "cache"]


# ---------------------------------------------------------------------------
# AdvisorReport dataclass tests
# ---------------------------------------------------------------------------


class TestAdvisorReport:
    def test_empty_report(self):
        report = AdvisorReport()
        assert report.recommendations == []
        assert report.total_recommendations == 0
        assert report.critical_count == 0
        assert report.coverage_score == 0.0
        assert report.topology_insights == {}

    def test_report_with_data(self):
        report = AdvisorReport(
            recommendations=[
                ChaosRecommendation(
                    priority="critical", scenario_name="s1", scenario_id="s1",
                    reasoning="r", risk_if_untested="risk", estimated_blast_radius=2,
                )
            ],
            total_recommendations=1,
            critical_count=1,
            coverage_score=85.0,
            topology_insights={"density": 0.5},
        )
        assert report.total_recommendations == 1
        assert report.critical_count == 1
        assert report.coverage_score == 85.0


# ---------------------------------------------------------------------------
# SPOF Detection
# ---------------------------------------------------------------------------


class TestSPOFDetection:
    def test_detects_spof_in_simple_graph(self, simple_graph):
        engine = ChaosAdvisorEngine(simple_graph)
        report = engine.analyze()

        spof_recs = [r for r in report.recommendations if "SPOF" in r.scenario_name]
        # db and cache have replicas=1 and at least one dependent
        spof_ids = {r.target_components[0] for r in spof_recs}
        assert "db" in spof_ids
        assert "cache" in spof_ids

    def test_no_spof_in_redundant_graph(self, redundant_graph):
        engine = ChaosAdvisorEngine(redundant_graph)
        report = engine.analyze()

        spof_recs = [r for r in report.recommendations if "SPOF" in r.scenario_name]
        assert len(spof_recs) == 0

    def test_spof_is_critical_priority(self, simple_graph):
        engine = ChaosAdvisorEngine(simple_graph)
        report = engine.analyze()

        spof_recs = [r for r in report.recommendations if "SPOF" in r.scenario_name]
        for rec in spof_recs:
            assert rec.priority == "critical"

    def test_spof_blast_radius(self, simple_graph):
        engine = ChaosAdvisorEngine(simple_graph)
        report = engine.analyze()

        db_spof = [r for r in report.recommendations
                   if "SPOF" in r.scenario_name and "db" in r.target_components]
        assert len(db_spof) == 1
        # db failure should cascade to app and lb
        assert db_spof[0].estimated_blast_radius >= 1


# ---------------------------------------------------------------------------
# Bottleneck Detection
# ---------------------------------------------------------------------------


class TestBottleneckDetection:
    def test_detects_bottleneck_in_linear_chain(self, linear_chain_graph):
        engine = ChaosAdvisorEngine(linear_chain_graph)
        report = engine.analyze()

        bottleneck_recs = [r for r in report.recommendations if "Bottleneck" in r.scenario_name]
        # In a linear chain, middle nodes should have high centrality
        assert len(bottleneck_recs) >= 1

    def test_bottleneck_is_high_priority(self, linear_chain_graph):
        engine = ChaosAdvisorEngine(linear_chain_graph)
        report = engine.analyze()

        bottleneck_recs = [r for r in report.recommendations if "Bottleneck" in r.scenario_name]
        for rec in bottleneck_recs:
            assert rec.priority == "high"


# ---------------------------------------------------------------------------
# Combination Failures
# ---------------------------------------------------------------------------


class TestCombinationFailures:
    def test_suggests_pairwise_combinations(self, simple_graph):
        engine = ChaosAdvisorEngine(simple_graph)
        report = engine.analyze()

        combo_recs = [r for r in report.recommendations if "Combination" in r.scenario_name]
        # Should have combinations for top-3 critical components
        assert len(combo_recs) >= 1

    def test_combination_targets_two_components(self, simple_graph):
        engine = ChaosAdvisorEngine(simple_graph)
        report = engine.analyze()

        combo_recs = [r for r in report.recommendations if "Combination" in r.scenario_name]
        for rec in combo_recs:
            assert len(rec.target_components) == 2

    def test_combination_priority_is_high(self, simple_graph):
        engine = ChaosAdvisorEngine(simple_graph)
        report = engine.analyze()

        combo_recs = [r for r in report.recommendations if "Combination" in r.scenario_name]
        for rec in combo_recs:
            assert rec.priority == "high"


# ---------------------------------------------------------------------------
# Missing Patterns
# ---------------------------------------------------------------------------


class TestMissingPatterns:
    def test_detects_missing_db_patterns(self, simple_graph):
        engine = ChaosAdvisorEngine(simple_graph)
        report = engine.analyze()

        db_missing = [
            r for r in report.recommendations
            if "Missing test" in r.scenario_name and "db" in r.target_components
        ]
        # DB should have recommended: connection_pool_exhaustion, disk_full, etc.
        fault_types = {r.scenario_name for r in db_missing}
        assert any("connection_pool_exhaustion" in ft for ft in fault_types)
        assert any("disk_full" in ft for ft in fault_types)

    def test_missing_patterns_are_medium_priority(self, simple_graph):
        engine = ChaosAdvisorEngine(simple_graph)
        report = engine.analyze()

        missing_recs = [r for r in report.recommendations if "Missing test" in r.scenario_name]
        for rec in missing_recs:
            assert rec.priority == "medium"


# ---------------------------------------------------------------------------
# Topology Insights
# ---------------------------------------------------------------------------


class TestTopologyInsights:
    def test_insights_contain_expected_keys(self, simple_graph):
        engine = ChaosAdvisorEngine(simple_graph)
        report = engine.analyze()

        insights = report.topology_insights
        assert "num_nodes" in insights
        assert "num_edges" in insights
        assert "density" in insights
        assert "longest_path" in insights
        assert "longest_path_length" in insights
        assert "most_connected_component" in insights
        assert "most_connected_degree" in insights
        assert "average_degree" in insights

    def test_insights_values_correct(self, simple_graph):
        engine = ChaosAdvisorEngine(simple_graph)
        report = engine.analyze()

        insights = report.topology_insights
        assert insights["num_nodes"] == 4
        assert insights["num_edges"] == 3
        assert insights["density"] > 0
        assert insights["longest_path_length"] >= 1

    def test_empty_graph_insights(self, empty_graph):
        engine = ChaosAdvisorEngine(empty_graph)
        report = engine.analyze()

        insights = report.topology_insights
        assert insights["num_nodes"] == 0
        assert insights["num_edges"] == 0
        assert insights["density"] == 0.0

    def test_linear_chain_longest_path(self, linear_chain_graph):
        engine = ChaosAdvisorEngine(linear_chain_graph)
        report = engine.analyze()

        insights = report.topology_insights
        assert insights["longest_path_length"] == 4  # lb -> app -> db -> storage


# ---------------------------------------------------------------------------
# Coverage Score
# ---------------------------------------------------------------------------


class TestCoverageScore:
    def test_empty_graph_full_coverage(self, empty_graph):
        engine = ChaosAdvisorEngine(empty_graph)
        report = engine.analyze()
        # No components = no recommendations = 100% coverage
        assert report.coverage_score == 100.0

    def test_redundant_graph_no_critical_recommendations(self, redundant_graph):
        engine = ChaosAdvisorEngine(redundant_graph)
        report = engine.analyze()
        # No SPOFs in redundant graph, so no critical recommendations
        assert report.critical_count == 0

    def test_simple_graph_has_critical_recommendations(self, simple_graph):
        engine = ChaosAdvisorEngine(simple_graph)
        report = engine.analyze()
        # Simple graph has SPOFs, so there should be critical recommendations
        assert report.critical_count > 0
        assert report.coverage_score < 100.0

    def test_coverage_score_bounded(self, simple_graph):
        engine = ChaosAdvisorEngine(simple_graph)
        report = engine.analyze()
        assert 0.0 <= report.coverage_score <= 100.0


# ---------------------------------------------------------------------------
# Sorting
# ---------------------------------------------------------------------------


class TestSorting:
    def test_recommendations_sorted_by_priority(self, simple_graph):
        engine = ChaosAdvisorEngine(simple_graph)
        report = engine.analyze()

        priority_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        for i in range(len(report.recommendations) - 1):
            current = priority_order.get(report.recommendations[i].priority, 99)
            next_p = priority_order.get(report.recommendations[i + 1].priority, 99)
            assert current <= next_p


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestBottleneckNoneComponent:
    def test_bottleneck_skips_none_comp(self):
        """Test line 224: _detect_bottlenecks skips components where get_component returns None."""
        # This is implicitly tested when the graph is consistent, but we verify
        # that the method works correctly for a valid graph
        graph = InfraGraph()
        graph.add_component(Component(
            id="a", name="A", type=ComponentType.APP_SERVER, replicas=1,
        ))
        graph.add_component(Component(
            id="b", name="B", type=ComponentType.APP_SERVER, replicas=1,
        ))
        graph.add_dependency(Dependency(source_id="a", target_id="b"))
        engine = ChaosAdvisorEngine(graph)
        report = engine.analyze()
        # Should not crash even if internal graph state is odd
        assert isinstance(report, AdvisorReport)

    def test_bottleneck_no_bottleneck_small_graph(self):
        """Test line 213: empty centrality dict returns no bottleneck recs."""
        graph = InfraGraph()
        graph.add_component(Component(
            id="solo", name="Solo", type=ComponentType.APP_SERVER, replicas=1,
        ))
        engine = ChaosAdvisorEngine(graph)
        report = engine.analyze()
        bottleneck_recs = [r for r in report.recommendations if "Bottleneck" in r.scenario_name]
        assert len(bottleneck_recs) == 0


class TestTopologyInsightsEdgeCases:
    def test_non_dag_longest_path(self):
        """Test lines 353-354: longest_path for cyclic (non-DAG) graph returns empty."""
        graph = InfraGraph()
        graph.add_component(Component(id="a", name="A", type=ComponentType.APP_SERVER, replicas=1))
        graph.add_component(Component(id="b", name="B", type=ComponentType.APP_SERVER, replicas=1))
        graph.add_dependency(Dependency(source_id="a", target_id="b"))
        graph.add_dependency(Dependency(source_id="b", target_id="a"))
        engine = ChaosAdvisorEngine(graph)
        report = engine.analyze()
        # Cyclic graph -> longest_path should be empty via lines 353-354
        assert report.topology_insights["longest_path"] == []
        assert report.topology_insights["longest_path_length"] == 0

    def test_exception_in_longest_path(self):
        """Test lines 355-357: exception during longest_path calculation is caught."""
        import unittest.mock as mock
        graph = InfraGraph()
        graph.add_component(Component(id="a", name="A", type=ComponentType.APP_SERVER, replicas=1))
        graph.add_component(Component(id="b", name="B", type=ComponentType.APP_SERVER, replicas=1))
        graph.add_dependency(Dependency(source_id="a", target_id="b"))

        engine = ChaosAdvisorEngine(graph)
        # Patch nx.dag_longest_path to raise an exception
        import networkx as nx
        with mock.patch.object(nx, "dag_longest_path", side_effect=RuntimeError("boom")):
            report = engine.analyze()
        assert report.topology_insights["longest_path"] == []
        assert report.topology_insights["longest_path_length"] == 0


class TestCoverageScoreLowPriority:
    def test_low_priority_penalty(self):
        """Test line 405: 'low' priority recommendations penalize by 1."""
        engine = ChaosAdvisorEngine.__new__(ChaosAdvisorEngine)
        # Create a recommendation with 'low' priority
        rec = ChaosRecommendation(
            priority="low",
            scenario_name="Test",
            scenario_id="t1",
            reasoning="r",
            risk_if_untested="risk",
            estimated_blast_radius=1,
        )
        score = engine._compute_coverage_score([rec])
        assert score == 99.0  # 100 - 1


class TestBottleneckEmptyCentralityMocked:
    def test_empty_centrality_returns_no_recs(self):
        """Test line 213: empty centrality dict returns no bottleneck recs (mocked)."""
        import unittest.mock as mock
        import networkx as nx

        graph = InfraGraph()
        graph.add_component(Component(id="a", name="A", type=ComponentType.APP_SERVER, replicas=1))
        graph.add_component(Component(id="b", name="B", type=ComponentType.APP_SERVER, replicas=1))
        graph.add_dependency(Dependency(source_id="a", target_id="b"))
        engine = ChaosAdvisorEngine(graph)
        # Mock betweenness_centrality to return empty dict
        with mock.patch.object(nx, "betweenness_centrality", return_value={}):
            recs = engine._detect_bottlenecks()
        assert recs == []

    def test_bottleneck_skips_none_comp_mocked(self):
        """Test line 224: _detect_bottlenecks skips nodes where get_component returns None."""
        import unittest.mock as mock
        import networkx as nx

        graph = InfraGraph()
        graph.add_component(Component(id="a", name="A", type=ComponentType.APP_SERVER, replicas=1))
        graph.add_component(Component(id="b", name="B", type=ComponentType.APP_SERVER, replicas=1))
        graph.add_dependency(Dependency(source_id="a", target_id="b"))
        engine = ChaosAdvisorEngine(graph)
        # Mock centrality to return a high score for a fake node
        with mock.patch.object(nx, "betweenness_centrality", return_value={"fake_node": 0.5, "a": 0.0}):
            recs = engine._detect_bottlenecks()
        # fake_node should be skipped (get_component returns None)
        # "a" has centrality < 0.1 so it breaks the loop
        assert all("fake_node" not in r.scenario_name for r in recs)


class TestEdgeCases:
    def test_single_node_no_spof(self, single_node_graph):
        """A single node with no dependents should not be flagged as SPOF."""
        engine = ChaosAdvisorEngine(single_node_graph)
        report = engine.analyze()

        spof_recs = [r for r in report.recommendations if "SPOF" in r.scenario_name]
        assert len(spof_recs) == 0

    def test_empty_graph_no_recommendations(self, empty_graph):
        engine = ChaosAdvisorEngine(empty_graph)
        report = engine.analyze()
        assert report.total_recommendations == 0
        assert report.critical_count == 0

    def test_analyze_returns_advisor_report(self, simple_graph):
        engine = ChaosAdvisorEngine(simple_graph)
        report = engine.analyze()
        assert isinstance(report, AdvisorReport)
