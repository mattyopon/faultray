"""Tests for dependency risk analyzer."""

from __future__ import annotations

import pytest

from faultray.model.components import (
    CircuitBreakerConfig,
    Component,
    ComponentType,
    Dependency,
    FailoverConfig,
    HealthStatus,
    RetryStrategy,
)
from faultray.model.graph import InfraGraph
from faultray.simulator.dependency_risk import (
    CouplingType,
    DependencyRisk,
    DependencyRiskAnalyzer,
    DependencyRiskLevel,
    DependencyRiskReport,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _comp(
    cid: str,
    name: str | None = None,
    ctype: ComponentType = ComponentType.APP_SERVER,
    replicas: int = 1,
    health: HealthStatus = HealthStatus.HEALTHY,
    failover: bool = False,
) -> Component:
    c = Component(
        id=cid,
        name=name or cid,
        type=ctype,
        replicas=replicas,
        failover=FailoverConfig(enabled=failover),
    )
    c.health = health
    return c


def _chain_graph() -> InfraGraph:
    """LB -> API -> DB chain."""
    g = InfraGraph()
    g.add_component(_comp("lb", "LB", ComponentType.LOAD_BALANCER, replicas=2))
    g.add_component(_comp("api", "API", replicas=3))
    g.add_component(_comp("db", "DB", ComponentType.DATABASE))
    g.add_dependency(Dependency(source_id="lb", target_id="api"))
    g.add_dependency(Dependency(source_id="api", target_id="db"))
    return g


def _dep(
    source: str,
    target: str,
    dep_type: str = "requires",
    cb: bool = False,
    retry: bool = False,
) -> Dependency:
    return Dependency(
        source_id=source,
        target_id=target,
        dependency_type=dep_type,
        circuit_breaker=CircuitBreakerConfig(enabled=cb),
        retry_strategy=RetryStrategy(enabled=retry),
    )


# ---------------------------------------------------------------------------
# Tests: Enums
# ---------------------------------------------------------------------------


class TestEnums:
    def test_risk_level_values(self):
        assert DependencyRiskLevel.CRITICAL.value == "critical"
        assert DependencyRiskLevel.HIGH.value == "high"
        assert DependencyRiskLevel.MEDIUM.value == "medium"
        assert DependencyRiskLevel.LOW.value == "low"
        assert DependencyRiskLevel.MINIMAL.value == "minimal"

    def test_coupling_type_values(self):
        assert CouplingType.TIGHT.value == "tight"
        assert CouplingType.LOOSE.value == "loose"
        assert CouplingType.ASYNC.value == "async"
        assert CouplingType.SYNC.value == "sync"

    def test_risk_level_is_str_enum(self):
        assert isinstance(DependencyRiskLevel.CRITICAL, str)

    def test_coupling_type_is_str_enum(self):
        assert isinstance(CouplingType.TIGHT, str)


# ---------------------------------------------------------------------------
# Tests: Single dependency analysis
# ---------------------------------------------------------------------------


class TestAnalyzeDependency:
    def test_basic_analysis_returns_risk(self):
        g = _chain_graph()
        analyzer = DependencyRiskAnalyzer()
        risk = analyzer.analyze_dependency(g, "api", "db")
        assert isinstance(risk, DependencyRisk)
        assert risk.source_id == "api"
        assert risk.target_id == "db"
        assert 0 <= risk.risk_score <= 100

    def test_no_circuit_breaker_adds_factor(self):
        g = InfraGraph()
        g.add_component(_comp("a"))
        g.add_component(_comp("b"))
        g.add_dependency(_dep("a", "b", cb=False))
        analyzer = DependencyRiskAnalyzer()
        risk = analyzer.analyze_dependency(g, "a", "b")
        assert any("circuit breaker" in f.lower() for f in risk.factors)

    def test_with_circuit_breaker_no_cb_factor(self):
        g = InfraGraph()
        g.add_component(_comp("a"))
        g.add_component(_comp("b"))
        g.add_dependency(_dep("a", "b", cb=True))
        analyzer = DependencyRiskAnalyzer()
        risk = analyzer.analyze_dependency(g, "a", "b")
        assert not any("circuit breaker" in f.lower() for f in risk.factors)

    def test_circuit_breaker_reduces_score(self):
        g1 = InfraGraph()
        g1.add_component(_comp("a"))
        g1.add_component(_comp("b"))
        g1.add_dependency(_dep("a", "b", cb=False))

        g2 = InfraGraph()
        g2.add_component(_comp("a"))
        g2.add_component(_comp("b"))
        g2.add_dependency(_dep("a", "b", cb=True))

        analyzer = DependencyRiskAnalyzer()
        r1 = analyzer.analyze_dependency(g1, "a", "b")
        r2 = analyzer.analyze_dependency(g2, "a", "b")
        assert r2.risk_score < r1.risk_score

    def test_no_retry_adds_factor(self):
        g = InfraGraph()
        g.add_component(_comp("a"))
        g.add_component(_comp("b"))
        g.add_dependency(_dep("a", "b", retry=False))
        analyzer = DependencyRiskAnalyzer()
        risk = analyzer.analyze_dependency(g, "a", "b")
        assert any("retry" in f.lower() for f in risk.factors)

    def test_with_retry_no_retry_factor(self):
        g = InfraGraph()
        g.add_component(_comp("a"))
        g.add_component(_comp("b"))
        g.add_dependency(_dep("a", "b", retry=True))
        analyzer = DependencyRiskAnalyzer()
        risk = analyzer.analyze_dependency(g, "a", "b")
        assert not any("retry strategy" in f.lower() for f in risk.factors)

    def test_target_single_instance_adds_factor(self):
        g = InfraGraph()
        g.add_component(_comp("a"))
        g.add_component(_comp("b", replicas=1))
        g.add_dependency(_dep("a", "b"))
        analyzer = DependencyRiskAnalyzer()
        risk = analyzer.analyze_dependency(g, "a", "b")
        assert any("no replicas" in f.lower() for f in risk.factors)

    def test_target_with_replicas_no_replica_factor(self):
        g = InfraGraph()
        g.add_component(_comp("a"))
        g.add_component(_comp("b", replicas=3))
        g.add_dependency(_dep("a", "b"))
        analyzer = DependencyRiskAnalyzer()
        risk = analyzer.analyze_dependency(g, "a", "b")
        assert not any("no replicas" in f.lower() for f in risk.factors)

    def test_target_no_failover_adds_factor(self):
        g = InfraGraph()
        g.add_component(_comp("a"))
        g.add_component(_comp("b", failover=False))
        g.add_dependency(_dep("a", "b"))
        analyzer = DependencyRiskAnalyzer()
        risk = analyzer.analyze_dependency(g, "a", "b")
        assert any("failover" in f.lower() for f in risk.factors)

    def test_target_with_failover_no_failover_factor(self):
        g = InfraGraph()
        g.add_component(_comp("a"))
        g.add_component(_comp("b", failover=True))
        g.add_dependency(_dep("a", "b"))
        analyzer = DependencyRiskAnalyzer()
        risk = analyzer.analyze_dependency(g, "a", "b")
        assert not any("no failover" in f.lower() for f in risk.factors)

    def test_tight_coupling_sync_requires(self):
        g = InfraGraph()
        g.add_component(_comp("a"))
        g.add_component(_comp("b"))
        g.add_dependency(_dep("a", "b", dep_type="requires", cb=False, retry=False))
        analyzer = DependencyRiskAnalyzer()
        risk = analyzer.analyze_dependency(g, "a", "b")
        assert risk.coupling_type == CouplingType.TIGHT

    def test_loose_coupling_with_protections(self):
        g = InfraGraph()
        g.add_component(_comp("a"))
        g.add_component(_comp("b"))
        g.add_dependency(_dep("a", "b", dep_type="requires", cb=True, retry=True))
        analyzer = DependencyRiskAnalyzer()
        risk = analyzer.analyze_dependency(g, "a", "b")
        assert risk.coupling_type == CouplingType.LOOSE

    def test_async_coupling(self):
        g = InfraGraph()
        g.add_component(_comp("a"))
        g.add_component(_comp("b"))
        g.add_dependency(_dep("a", "b", dep_type="async"))
        analyzer = DependencyRiskAnalyzer()
        risk = analyzer.analyze_dependency(g, "a", "b")
        assert risk.coupling_type == CouplingType.ASYNC

    def test_unhealthy_target_adds_factor(self):
        g = InfraGraph()
        g.add_component(_comp("a"))
        g.add_component(_comp("b", health=HealthStatus.DOWN))
        g.add_dependency(_dep("a", "b"))
        analyzer = DependencyRiskAnalyzer()
        risk = analyzer.analyze_dependency(g, "a", "b")
        assert any("health" in f.lower() for f in risk.factors)

    def test_mitigation_present_for_each_factor(self):
        g = InfraGraph()
        g.add_component(_comp("a"))
        g.add_component(_comp("b"))
        g.add_dependency(_dep("a", "b"))
        analyzer = DependencyRiskAnalyzer()
        risk = analyzer.analyze_dependency(g, "a", "b")
        # Each risk factor should have at least one corresponding mitigation
        assert len(risk.mitigation) >= 1

    def test_risk_score_capped_at_100(self):
        g = InfraGraph()
        # Build a maximally risky scenario
        g.add_component(_comp("a"))
        g.add_component(_comp("b", health=HealthStatus.DOWN))
        # Add many components that a depends on for fan-out
        for i in range(5):
            g.add_component(_comp(f"x{i}"))
            g.add_dependency(_dep("a", f"x{i}"))
        g.add_dependency(_dep("a", "b"))
        analyzer = DependencyRiskAnalyzer()
        risk = analyzer.analyze_dependency(g, "a", "b")
        assert risk.risk_score <= 100


# ---------------------------------------------------------------------------
# Tests: Fan-out risk
# ---------------------------------------------------------------------------


class TestFanOut:
    def test_high_fan_out_detected(self):
        g = InfraGraph()
        g.add_component(_comp("src"))
        for i in range(5):
            g.add_component(_comp(f"t{i}"))
            g.add_dependency(_dep("src", f"t{i}"))
        analyzer = DependencyRiskAnalyzer()
        risk = analyzer.analyze_dependency(g, "src", "t0")
        assert any("fan-out" in f.lower() for f in risk.factors)

    def test_low_fan_out_not_flagged(self):
        g = InfraGraph()
        g.add_component(_comp("src"))
        g.add_component(_comp("t0"))
        g.add_dependency(_dep("src", "t0"))
        analyzer = DependencyRiskAnalyzer()
        risk = analyzer.analyze_dependency(g, "src", "t0")
        assert not any("fan-out" in f.lower() for f in risk.factors)


# ---------------------------------------------------------------------------
# Tests: Critical path detection
# ---------------------------------------------------------------------------


class TestCriticalPaths:
    def test_chain_has_critical_path(self):
        g = _chain_graph()
        analyzer = DependencyRiskAnalyzer()
        paths = analyzer.find_critical_paths(g)
        assert len(paths) >= 1
        # The chain lb->api->db should be the longest
        assert len(paths[0]) == 3

    def test_longer_chain_is_first(self):
        g = InfraGraph()
        g.add_component(_comp("a"))
        g.add_component(_comp("b"))
        g.add_component(_comp("c"))
        g.add_component(_comp("d"))
        g.add_dependency(_dep("a", "b"))
        g.add_dependency(_dep("b", "c"))
        g.add_dependency(_dep("c", "d"))
        analyzer = DependencyRiskAnalyzer()
        paths = analyzer.find_critical_paths(g)
        assert paths[0] == ["a", "b", "c", "d"]

    def test_empty_graph_no_paths(self):
        g = InfraGraph()
        analyzer = DependencyRiskAnalyzer()
        paths = analyzer.find_critical_paths(g)
        assert paths == []

    def test_single_component_no_paths(self):
        g = InfraGraph()
        g.add_component(_comp("only"))
        analyzer = DependencyRiskAnalyzer()
        paths = analyzer.find_critical_paths(g)
        assert paths == []


# ---------------------------------------------------------------------------
# Tests: SPOF detection
# ---------------------------------------------------------------------------


class TestSPOF:
    def test_single_replica_no_failover_is_spof(self):
        g = _chain_graph()
        analyzer = DependencyRiskAnalyzer()
        spofs = analyzer.find_spofs(g)
        # db has replicas=1, no failover, and api depends on it
        assert "db" in spofs

    def test_multi_replica_not_spof(self):
        g = InfraGraph()
        g.add_component(_comp("a"))
        g.add_component(_comp("b", replicas=3))
        g.add_dependency(_dep("a", "b"))
        analyzer = DependencyRiskAnalyzer()
        spofs = analyzer.find_spofs(g)
        assert "b" not in spofs

    def test_failover_enabled_not_spof(self):
        g = InfraGraph()
        g.add_component(_comp("a"))
        g.add_component(_comp("b", failover=True))
        g.add_dependency(_dep("a", "b"))
        analyzer = DependencyRiskAnalyzer()
        spofs = analyzer.find_spofs(g)
        assert "b" not in spofs

    def test_no_dependents_not_spof(self):
        g = InfraGraph()
        g.add_component(_comp("leaf"))
        analyzer = DependencyRiskAnalyzer()
        spofs = analyzer.find_spofs(g)
        assert "leaf" not in spofs

    def test_multiple_spofs(self):
        g = InfraGraph()
        g.add_component(_comp("front"))
        g.add_component(_comp("api"))
        g.add_component(_comp("db"))
        g.add_component(_comp("cache"))
        g.add_dependency(_dep("front", "api"))
        g.add_dependency(_dep("api", "db"))
        g.add_dependency(_dep("api", "cache"))
        analyzer = DependencyRiskAnalyzer()
        spofs = analyzer.find_spofs(g)
        assert "api" in spofs
        assert "db" in spofs
        assert "cache" in spofs


# ---------------------------------------------------------------------------
# Tests: Circular dependency detection
# ---------------------------------------------------------------------------


class TestCircularDependencies:
    def test_no_cycle_returns_empty(self):
        g = _chain_graph()
        analyzer = DependencyRiskAnalyzer()
        report = analyzer.analyze(g)
        assert report.circular_dependencies == []

    def test_cycle_detected(self):
        g = InfraGraph()
        g.add_component(_comp("a"))
        g.add_component(_comp("b"))
        g.add_dependency(_dep("a", "b"))
        g.add_dependency(_dep("b", "a"))
        analyzer = DependencyRiskAnalyzer()
        report = analyzer.analyze(g)
        assert len(report.circular_dependencies) >= 1
        # The cycle should contain both a and b
        cycle_members = set()
        for cycle in report.circular_dependencies:
            cycle_members.update(cycle)
        assert "a" in cycle_members
        assert "b" in cycle_members

    def test_three_node_cycle(self):
        g = InfraGraph()
        g.add_component(_comp("a"))
        g.add_component(_comp("b"))
        g.add_component(_comp("c"))
        g.add_dependency(_dep("a", "b"))
        g.add_dependency(_dep("b", "c"))
        g.add_dependency(_dep("c", "a"))
        analyzer = DependencyRiskAnalyzer()
        report = analyzer.analyze(g)
        assert len(report.circular_dependencies) >= 1


# ---------------------------------------------------------------------------
# Tests: Full report (analyze)
# ---------------------------------------------------------------------------


class TestFullReport:
    def test_report_structure(self):
        g = _chain_graph()
        analyzer = DependencyRiskAnalyzer()
        report = analyzer.analyze(g)
        assert isinstance(report, DependencyRiskReport)
        assert isinstance(report.risks, list)
        assert isinstance(report.overall_risk_score, float)
        assert isinstance(report.critical_paths, list)
        assert isinstance(report.circular_dependencies, list)
        assert isinstance(report.single_point_of_failures, list)
        assert isinstance(report.recommendations, list)

    def test_report_risks_match_edges(self):
        g = _chain_graph()
        analyzer = DependencyRiskAnalyzer()
        report = analyzer.analyze(g)
        edges = g.all_dependency_edges()
        assert len(report.risks) == len(edges)

    def test_overall_score_is_max_of_risks(self):
        g = _chain_graph()
        analyzer = DependencyRiskAnalyzer()
        report = analyzer.analyze(g)
        if report.risks:
            max_score = max(r.risk_score for r in report.risks)
            assert report.overall_risk_score == max_score

    def test_empty_graph_report(self):
        g = InfraGraph()
        analyzer = DependencyRiskAnalyzer()
        report = analyzer.analyze(g)
        assert report.overall_risk_score == 0.0
        assert report.risks == []
        assert report.critical_paths == []
        assert report.circular_dependencies == []
        assert report.single_point_of_failures == []

    def test_single_component_report(self):
        g = InfraGraph()
        g.add_component(_comp("only"))
        analyzer = DependencyRiskAnalyzer()
        report = analyzer.analyze(g)
        assert report.overall_risk_score == 0.0
        assert report.risks == []


# ---------------------------------------------------------------------------
# Tests: Recommendations
# ---------------------------------------------------------------------------


class TestRecommendations:
    def test_spof_recommendation(self):
        g = _chain_graph()
        analyzer = DependencyRiskAnalyzer()
        report = analyzer.analyze(g)
        assert any("single point" in r.lower() for r in report.recommendations)

    def test_circuit_breaker_recommendation(self):
        g = _chain_graph()
        analyzer = DependencyRiskAnalyzer()
        report = analyzer.analyze(g)
        assert any("circuit breaker" in r.lower() for r in report.recommendations)

    def test_retry_recommendation(self):
        g = _chain_graph()
        analyzer = DependencyRiskAnalyzer()
        report = analyzer.analyze(g)
        assert any("retry" in r.lower() for r in report.recommendations)

    def test_cycle_recommendation(self):
        g = InfraGraph()
        g.add_component(_comp("a"))
        g.add_component(_comp("b"))
        g.add_dependency(_dep("a", "b"))
        g.add_dependency(_dep("b", "a"))
        analyzer = DependencyRiskAnalyzer()
        report = analyzer.analyze(g)
        assert any("circular" in r.lower() for r in report.recommendations)

    def test_fan_out_recommendation(self):
        g = InfraGraph()
        g.add_component(_comp("src"))
        for i in range(5):
            g.add_component(_comp(f"t{i}"))
            g.add_dependency(_dep("src", f"t{i}"))
        analyzer = DependencyRiskAnalyzer()
        report = analyzer.analyze(g)
        assert any("fan-out" in r.lower() for r in report.recommendations)

    def test_long_chain_recommendation(self):
        g = InfraGraph()
        ids = [f"n{i}" for i in range(5)]
        for cid in ids:
            g.add_component(_comp(cid))
        for i in range(len(ids) - 1):
            g.add_dependency(_dep(ids[i], ids[i + 1]))
        analyzer = DependencyRiskAnalyzer()
        report = analyzer.analyze(g)
        # Chain length is 5 => should trigger recommendation (>=4)
        assert any("chain" in r.lower() for r in report.recommendations)

    def test_fully_protected_graph_fewer_recommendations(self):
        g = InfraGraph()
        g.add_component(_comp("a", replicas=3, failover=True))
        g.add_component(_comp("b", replicas=3, failover=True))
        g.add_dependency(_dep("a", "b", cb=True, retry=True))
        analyzer = DependencyRiskAnalyzer()
        report = analyzer.analyze(g)
        # No SPOFs, has CB, has retry -- very few recommendations
        assert not any("single point" in r.lower() for r in report.recommendations)
        assert not any("circuit breaker" in r.lower() for r in report.recommendations)
        assert not any("retry" in r.lower() for r in report.recommendations)


# ---------------------------------------------------------------------------
# Tests: Complex topologies
# ---------------------------------------------------------------------------


class TestComplexTopologies:
    def test_diamond_topology(self):
        """A -> B, A -> C, B -> D, C -> D."""
        g = InfraGraph()
        g.add_component(_comp("a"))
        g.add_component(_comp("b"))
        g.add_component(_comp("c"))
        g.add_component(_comp("d"))
        g.add_dependency(_dep("a", "b"))
        g.add_dependency(_dep("a", "c"))
        g.add_dependency(_dep("b", "d"))
        g.add_dependency(_dep("c", "d"))
        analyzer = DependencyRiskAnalyzer()
        report = analyzer.analyze(g)
        assert len(report.risks) == 4
        # d is a SPOF (b and c depend on it)
        assert "d" in report.single_point_of_failures

    def test_star_topology(self):
        """Hub -> spoke1, Hub -> spoke2, Hub -> spoke3, Hub -> spoke4."""
        g = InfraGraph()
        g.add_component(_comp("hub"))
        for i in range(4):
            g.add_component(_comp(f"spoke{i}"))
            g.add_dependency(_dep("hub", f"spoke{i}"))
        analyzer = DependencyRiskAnalyzer()
        report = analyzer.analyze(g)
        assert len(report.risks) == 4
        # fan-out should be detected
        assert any("fan-out" in r.lower() for r in report.recommendations)

    def test_disconnected_components(self):
        """Two independent chains with no connection."""
        g = InfraGraph()
        g.add_component(_comp("a1"))
        g.add_component(_comp("a2"))
        g.add_dependency(_dep("a1", "a2"))
        g.add_component(_comp("b1"))
        g.add_component(_comp("b2"))
        g.add_dependency(_dep("b1", "b2"))
        analyzer = DependencyRiskAnalyzer()
        report = analyzer.analyze(g)
        assert len(report.risks) == 2


# ---------------------------------------------------------------------------
# Tests: Risk level mapping
# ---------------------------------------------------------------------------


class TestRiskLevelMapping:
    def test_score_to_level_critical(self):
        analyzer = DependencyRiskAnalyzer()
        assert analyzer._score_to_level(70) == DependencyRiskLevel.CRITICAL
        assert analyzer._score_to_level(100) == DependencyRiskLevel.CRITICAL

    def test_score_to_level_high(self):
        analyzer = DependencyRiskAnalyzer()
        assert analyzer._score_to_level(50) == DependencyRiskLevel.HIGH
        assert analyzer._score_to_level(69) == DependencyRiskLevel.HIGH

    def test_score_to_level_medium(self):
        analyzer = DependencyRiskAnalyzer()
        assert analyzer._score_to_level(30) == DependencyRiskLevel.MEDIUM
        assert analyzer._score_to_level(49) == DependencyRiskLevel.MEDIUM

    def test_score_to_level_low(self):
        analyzer = DependencyRiskAnalyzer()
        assert analyzer._score_to_level(15) == DependencyRiskLevel.LOW
        assert analyzer._score_to_level(29) == DependencyRiskLevel.LOW

    def test_score_to_level_minimal(self):
        analyzer = DependencyRiskAnalyzer()
        assert analyzer._score_to_level(0) == DependencyRiskLevel.MINIMAL
        assert analyzer._score_to_level(14) == DependencyRiskLevel.MINIMAL


# ---------------------------------------------------------------------------
# Tests: Coverage gaps — lines 176, 239-242, 281, 295, 305-306
# ---------------------------------------------------------------------------


class TestCoverageGaps:
    def test_optional_dependency_type_no_extra_risk(self):
        """An 'optional' dependency should add no extra risk score. [line 176]"""
        g = InfraGraph()
        g.add_component(_comp("a"))
        g.add_component(_comp("b"))
        g.add_dependency(_dep("a", "b", dep_type="optional"))
        analyzer = DependencyRiskAnalyzer()
        risk = analyzer.analyze_dependency(g, "a", "b")
        # Optional dep should not have "Hard 'requires' dependency" factor
        assert not any("requires" in f.lower() for f in risk.factors)
        # The score should still be valid
        assert 0 <= risk.risk_score <= 100

    def test_coupling_type_none_dep_returns_sync(self):
        """When dependency edge is None, coupling should be SYNC. [line 281]"""
        analyzer = DependencyRiskAnalyzer()
        coupling = analyzer._determine_coupling(None)
        assert coupling == CouplingType.SYNC

    def test_coupling_type_sync_non_requires(self):
        """A sync dependency that is not 'requires' and has no CB+retry
        should return SYNC. [line 295]"""
        # dep_type is default (not "async", not "requires"), no CB, no retry
        dep = _dep("a", "b", dep_type="optional", cb=False, retry=False)
        analyzer = DependencyRiskAnalyzer()
        coupling = analyzer._determine_coupling(dep)
        assert coupling == CouplingType.SYNC

    def test_analyze_dependency_with_missing_edge(self):
        """Analyzing a dependency with no actual edge in graph exercises
        the dep=None coupling path. [line 281 via analyze_dependency]"""
        g = InfraGraph()
        g.add_component(_comp("a"))
        g.add_component(_comp("b"))
        # No dependency edge between a and b
        analyzer = DependencyRiskAnalyzer()
        risk = analyzer.analyze_dependency(g, "a", "b")
        assert risk.coupling_type == CouplingType.SYNC

    def test_critical_paths_with_networkx_error_in_path_search(self):
        """Exercise the except nx.NetworkXError branches in
        find_critical_paths when path search hits issues. [lines 239-242]
        This is tested by having a graph with nodes but ensuring the
        entry/leaf logic works (the except catches errors from
        nx.all_simple_paths for disconnected entry/leaf pairs)."""
        g = InfraGraph()
        # Create two disconnected chains sharing entries/leaves logic
        g.add_component(_comp("a"))
        g.add_component(_comp("b"))
        g.add_component(_comp("c"))
        g.add_component(_comp("d"))
        g.add_dependency(_dep("a", "b"))
        g.add_dependency(_dep("c", "d"))
        analyzer = DependencyRiskAnalyzer()
        paths = analyzer.find_critical_paths(g)
        # Should find paths without error, even with disconnected subgraphs
        assert isinstance(paths, list)

    def test_find_circular_dependencies_returns_cycles(self):
        """Verify _find_circular_dependencies returns cycle data. [lines 305-306]"""
        g = InfraGraph()
        g.add_component(_comp("a"))
        g.add_component(_comp("b"))
        g.add_dependency(_dep("a", "b"))
        g.add_dependency(_dep("b", "a"))
        analyzer = DependencyRiskAnalyzer()
        cycles = analyzer._find_circular_dependencies(g)
        assert len(cycles) >= 1

    def test_find_circular_dependencies_no_cycle(self):
        """A DAG should return empty cycle list. [line 305-306 — normal path]"""
        g = _chain_graph()
        analyzer = DependencyRiskAnalyzer()
        cycles = analyzer._find_circular_dependencies(g)
        assert cycles == []

    def test_critical_paths_entry_equals_leaf_skipped(self):
        """When entry == leaf in path finding, the pair is skipped (line 234).
        A single-node graph where a node is both entry and leaf."""
        g = InfraGraph()
        g.add_component(_comp("solo"))
        analyzer = DependencyRiskAnalyzer()
        paths = analyzer.find_critical_paths(g)
        # Single node has no paths of length >= 2
        assert paths == []

    def test_critical_paths_networkx_error_in_all_simple_paths_outer(self):
        """Exercise except nx.NetworkXError in DAG branch. [lines 241-242]"""
        from unittest.mock import patch
        import networkx as nx

        g = InfraGraph()
        g.add_component(_comp("a"))
        g.add_component(_comp("b"))
        g.add_dependency(_dep("a", "b"))
        analyzer = DependencyRiskAnalyzer()

        def mock_all_simple_paths(*args, **kwargs):
            raise nx.NetworkXError("mocked error")

        with patch("networkx.all_simple_paths", side_effect=mock_all_simple_paths):
            paths = analyzer.find_critical_paths(g)
        assert isinstance(paths, list)

    def test_critical_paths_networkx_error_in_cyclic_graph(self):
        """Exercise except nx.NetworkXError in cyclic graph branch. [lines 239-240]
        When graph has cycles, the else block is entered. If all_simple_paths
        raises NetworkXError for a specific entry/leaf pair, it continues."""
        from unittest.mock import patch
        import networkx as nx

        g = InfraGraph()
        g.add_component(_comp("a"))
        g.add_component(_comp("b"))
        g.add_dependency(_dep("a", "b"))
        g.add_dependency(_dep("b", "a"))  # create cycle
        analyzer = DependencyRiskAnalyzer()

        def mock_all_simple_paths(*args, **kwargs):
            raise nx.NetworkXError("mocked error in cyclic path search")

        with patch("networkx.all_simple_paths", side_effect=mock_all_simple_paths):
            paths = analyzer.find_critical_paths(g)
        assert isinstance(paths, list)

    def test_find_circular_dependencies_networkx_error(self):
        """Exercise except nx.NetworkXError in _find_circular_dependencies. [lines 305-306]"""
        from unittest.mock import patch
        import networkx as nx

        g = InfraGraph()
        g.add_component(_comp("a"))
        g.add_component(_comp("b"))
        g.add_dependency(_dep("a", "b"))
        analyzer = DependencyRiskAnalyzer()

        def mock_simple_cycles(*args, **kwargs):
            raise nx.NetworkXError("mocked cycle error")

        with patch("networkx.simple_cycles", side_effect=mock_simple_cycles):
            cycles = analyzer._find_circular_dependencies(g)
        assert cycles == []
