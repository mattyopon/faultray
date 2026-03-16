"""Tests for Chaos A/B Testing Engine."""

from __future__ import annotations

import pytest

from faultray.model.components import (
    AutoScalingConfig,
    CircuitBreakerConfig,
    Component,
    ComponentType,
    Dependency,
    FailoverConfig,
    RetryStrategy,
)
from faultray.model.graph import InfraGraph
from faultray.simulator.ab_chaos import ABReport, ABResult, ChaosABTester
from faultray.simulator.scenarios import Fault, FaultType, Scenario


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _weak_graph() -> InfraGraph:
    """Build a weak graph with no resilience features."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="lb", name="Load Balancer", type=ComponentType.LOAD_BALANCER,
        replicas=1,
    ))
    graph.add_component(Component(
        id="app", name="App Server", type=ComponentType.APP_SERVER,
        replicas=1,
    ))
    graph.add_component(Component(
        id="db", name="Database", type=ComponentType.DATABASE,
        replicas=1,
    ))
    graph.add_dependency(Dependency(
        source_id="lb", target_id="app", dependency_type="requires",
    ))
    graph.add_dependency(Dependency(
        source_id="app", target_id="db", dependency_type="requires",
    ))
    return graph


def _strong_graph() -> InfraGraph:
    """Build a resilient graph with failover, circuit breakers, autoscaling."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="lb", name="Load Balancer", type=ComponentType.LOAD_BALANCER,
        replicas=2,
        failover=FailoverConfig(enabled=True),
        autoscaling=AutoScalingConfig(enabled=True, min_replicas=2, max_replicas=4),
    ))
    graph.add_component(Component(
        id="app", name="App Server", type=ComponentType.APP_SERVER,
        replicas=3,
        failover=FailoverConfig(enabled=True),
        autoscaling=AutoScalingConfig(enabled=True, min_replicas=2, max_replicas=10),
    ))
    graph.add_component(Component(
        id="db", name="Database", type=ComponentType.DATABASE,
        replicas=3,
        failover=FailoverConfig(enabled=True),
    ))
    graph.add_dependency(Dependency(
        source_id="lb", target_id="app", dependency_type="requires",
        circuit_breaker=CircuitBreakerConfig(enabled=True),
        retry_strategy=RetryStrategy(enabled=True),
    ))
    graph.add_dependency(Dependency(
        source_id="app", target_id="db", dependency_type="requires",
        circuit_breaker=CircuitBreakerConfig(enabled=True),
        retry_strategy=RetryStrategy(enabled=True),
    ))
    return graph


def _disjoint_graph() -> InfraGraph:
    """Build a graph with completely different component IDs."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="x_server", name="X Server", type=ComponentType.APP_SERVER,
    ))
    graph.add_component(Component(
        id="x_db", name="X DB", type=ComponentType.DATABASE,
    ))
    graph.add_dependency(Dependency(
        source_id="x_server", target_id="x_db", dependency_type="requires",
    ))
    return graph


def _make_scenario(target_id: str, name: str = "test-scenario") -> Scenario:
    return Scenario(
        id=f"test-{target_id}",
        name=name,
        description=f"Test fault on {target_id}",
        faults=[Fault(
            target_component_id=target_id,
            fault_type=FaultType.COMPONENT_DOWN,
            severity=1.0,
        )],
    )


# ---------------------------------------------------------------------------
# Tests: ChaosABTester
# ---------------------------------------------------------------------------


class TestChaosABTester:
    """Tests for the ChaosABTester class."""

    def test_strong_vs_weak_strong_wins(self):
        """Strong graph should outperform weak graph."""
        tester = ChaosABTester(
            _strong_graph(), _weak_graph(),
            name_a="Strong", name_b="Weak",
        )
        report = tester.test_default()
        assert isinstance(report, ABReport)
        assert report.scenarios_tested > 0
        # Strong architecture should generally win or tie
        assert report.a_wins >= report.b_wins

    def test_weak_vs_strong_weak_loses(self):
        """Weak graph (A) vs strong graph (B) -> B should win."""
        tester = ChaosABTester(
            _weak_graph(), _strong_graph(),
            name_a="Weak", name_b="Strong",
        )
        report = tester.test_default()
        assert report.scenarios_tested > 0
        assert report.b_wins >= report.a_wins

    def test_identical_graphs_tie(self):
        """Same graph compared against itself should produce mostly ties."""
        graph = _weak_graph()
        tester = ChaosABTester(graph, graph, name_a="Copy1", name_b="Copy2")
        report = tester.test_default()
        assert report.scenarios_tested > 0
        # With identical graphs, all should be ties
        assert report.ties == report.scenarios_tested
        assert report.overall_winner == "tie"

    def test_explicit_scenarios(self):
        """Test with explicitly provided scenarios."""
        tester = ChaosABTester(
            _strong_graph(), _weak_graph(),
            name_a="Strong", name_b="Weak",
        )
        scenarios = [
            _make_scenario("db", "DB failure"),
            _make_scenario("app", "App failure"),
        ]
        report = tester.test(scenarios=scenarios)
        assert report.scenarios_tested == 2

    def test_disjoint_graphs_no_common_scenarios(self):
        """Disjoint graphs share no components -> no scenarios tested."""
        tester = ChaosABTester(
            _weak_graph(), _disjoint_graph(),
            name_a="Normal", name_b="Disjoint",
        )
        report = tester.test_default()
        assert report.scenarios_tested == 0
        assert report.overall_winner == "tie"
        assert "No common scenarios" in report.recommendation

    def test_scenario_filtering(self):
        """Scenarios with targets not in both graphs should be filtered out."""
        tester = ChaosABTester(
            _weak_graph(), _strong_graph(),
        )
        # Scenario targeting a non-existent component
        invalid = _make_scenario("nonexistent", "Invalid scenario")
        valid = _make_scenario("app", "Valid scenario")
        report = tester.test(scenarios=[invalid, valid])
        assert report.scenarios_tested == 1

    def test_report_fields(self):
        """Verify all ABReport fields are populated."""
        tester = ChaosABTester(
            _strong_graph(), _weak_graph(),
            name_a="Alpha", name_b="Beta",
        )
        report = tester.test_default()

        assert report.variant_a_name == "Alpha"
        assert report.variant_b_name == "Beta"
        assert isinstance(report.scenarios_tested, int)
        assert isinstance(report.a_wins, int)
        assert isinstance(report.b_wins, int)
        assert isinstance(report.ties, int)
        assert report.overall_winner in ("A", "B", "tie")
        assert 0 <= report.variant_a_resilience <= 100
        assert 0 <= report.variant_b_resilience <= 100
        assert report.variant_a_avg_risk >= 0
        assert report.variant_b_avg_risk >= 0
        assert isinstance(report.recommendation, str)
        assert len(report.recommendation) > 0

    def test_win_counts_sum_to_total(self):
        """a_wins + b_wins + ties should equal scenarios_tested."""
        tester = ChaosABTester(_strong_graph(), _weak_graph())
        report = tester.test_default()
        assert report.a_wins + report.b_wins + report.ties == report.scenarios_tested

    def test_custom_names(self):
        """Custom variant names should appear in the report."""
        tester = ChaosABTester(
            _weak_graph(), _strong_graph(),
            name_a="v1-legacy", name_b="v2-modern",
        )
        report = tester.test_default()
        assert report.variant_a_name == "v1-legacy"
        assert report.variant_b_name == "v2-modern"


class TestABResult:
    """Tests for the ABResult dataclass."""

    def test_ab_result_fields(self):
        result = ABResult(
            scenario_name="Test",
            variant_a_score=3.5,
            variant_b_score=7.2,
            winner="A",
            difference=3.7,
        )
        assert result.scenario_name == "Test"
        assert result.variant_a_score == 3.5
        assert result.variant_b_score == 7.2
        assert result.winner == "A"
        assert result.difference == pytest.approx(3.7)


class TestABReport:
    """Tests for the ABReport dataclass."""

    def test_ab_report_defaults(self):
        report = ABReport(
            variant_a_name="A",
            variant_b_name="B",
            scenarios_tested=0,
            a_wins=0,
            b_wins=0,
            ties=0,
            overall_winner="tie",
            variant_a_resilience=50.0,
            variant_b_resilience=50.0,
            variant_a_avg_risk=0.0,
            variant_b_avg_risk=0.0,
        )
        assert report.results == []
        assert report.recommendation == ""


class TestRecommendation:
    """Tests for recommendation generation."""

    def test_recommendation_for_winner(self):
        tester = ChaosABTester(
            _strong_graph(), _weak_graph(),
            name_a="Strong", name_b="Weak",
        )
        report = tester.test_default()
        if report.overall_winner != "tie":
            assert "Recommend" in report.recommendation or "outperformed" in report.recommendation

    def test_recommendation_for_tie(self):
        graph = _weak_graph()
        tester = ChaosABTester(graph, graph)
        report = tester.test_default()
        assert "equally" in report.recommendation or "Both" in report.recommendation

    def test_recommendation_for_no_scenarios(self):
        tester = ChaosABTester(_weak_graph(), _disjoint_graph())
        report = tester.test_default()
        assert "No common scenarios" in report.recommendation


class TestEdgeCases:
    """Edge case tests."""

    def test_empty_graphs(self):
        """Two empty graphs should produce 0 scenarios."""
        graph_a = InfraGraph()
        graph_b = InfraGraph()
        tester = ChaosABTester(graph_a, graph_b)
        report = tester.test_default()
        assert report.scenarios_tested == 0

    def test_empty_scenario_list(self):
        """Empty explicit scenario list should produce empty report."""
        tester = ChaosABTester(_weak_graph(), _strong_graph())
        report = tester.test(scenarios=[])
        assert report.scenarios_tested == 0
        assert report.a_wins == 0
        assert report.b_wins == 0

    def test_single_scenario(self):
        """Single scenario should still produce a valid report."""
        tester = ChaosABTester(_strong_graph(), _weak_graph())
        scenarios = [_make_scenario("db", "Single DB failure")]
        report = tester.test(scenarios=scenarios)
        assert report.scenarios_tested == 1
        assert report.a_wins + report.b_wins + report.ties == 1
