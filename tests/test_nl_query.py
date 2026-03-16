"""Tests for Natural Language Query Engine."""

from __future__ import annotations

import pytest

from faultray.model.components import (
    AutoScalingConfig,
    Component,
    ComponentType,
    CostProfile,
    Dependency,
    FailoverConfig,
    ResourceMetrics,
)
from faultray.model.graph import InfraGraph
from faultray.nl_query import NaturalLanguageEngine, QueryResult


def _build_test_graph() -> InfraGraph:
    """Build a simple test infrastructure graph."""
    graph = InfraGraph()

    # Load balancer
    graph.add_component(Component(
        id="lb",
        name="Load Balancer",
        type=ComponentType.LOAD_BALANCER,
        replicas=2,
        failover=FailoverConfig(enabled=True, promotion_time_seconds=5),
    ))

    # App server
    graph.add_component(Component(
        id="app",
        name="App Server",
        type=ComponentType.APP_SERVER,
        replicas=3,
        autoscaling=AutoScalingConfig(enabled=True, min_replicas=2, max_replicas=10),
    ))

    # Database (single point of failure)
    graph.add_component(Component(
        id="postgres",
        name="PostgreSQL",
        type=ComponentType.DATABASE,
        replicas=1,
        cost_profile=CostProfile(
            hourly_infra_cost=50.0,
            revenue_per_minute=100.0,
            recovery_engineer_cost=200.0,
        ),
    ))

    # Cache
    graph.add_component(Component(
        id="redis",
        name="Redis Cache",
        type=ComponentType.CACHE,
        replicas=2,
        failover=FailoverConfig(enabled=True),
    ))

    # Dependencies
    graph.add_dependency(Dependency(
        source_id="lb", target_id="app", dependency_type="requires",
    ))
    graph.add_dependency(Dependency(
        source_id="app", target_id="postgres", dependency_type="requires",
    ))
    graph.add_dependency(Dependency(
        source_id="app", target_id="redis", dependency_type="optional",
    ))

    return graph


class TestNaturalLanguageEngine:
    """Test suite for NaturalLanguageEngine."""

    def test_component_down_query(self):
        """Test 'what happens if X goes down' query."""
        graph = _build_test_graph()
        engine = NaturalLanguageEngine(graph)

        result = engine.query("What happens if postgres goes down?")

        assert result.query_type == "component_down"
        assert "postgres" in result.components_matched
        assert result.scenario is not None
        assert result.result is not None
        assert "PostgreSQL" in result.interpreted_as or "postgres" in result.interpreted_as
        assert result.answer != ""

    def test_component_down_with_name(self):
        """Test component matching by display name."""
        graph = _build_test_graph()
        engine = NaturalLanguageEngine(graph)

        result = engine.query("What happens if the database crashes?")

        # Should match postgres (database type)
        assert result.query_type == "component_down"
        assert result.answer != ""

    def test_traffic_spike_query(self):
        """Test 'what happens if traffic spikes' query."""
        graph = _build_test_graph()
        engine = NaturalLanguageEngine(graph)

        result = engine.query("What happens if traffic spikes?")

        assert result.query_type == "traffic_spike"
        assert result.scenario is not None
        assert result.result is not None
        assert "traffic spike" in result.interpreted_as.lower()

    def test_traffic_spike_with_multiplier(self):
        """Test traffic spike with explicit multiplier."""
        graph = _build_test_graph()
        engine = NaturalLanguageEngine(graph)

        result = engine.query("What happens if traffic increases 10x?")

        assert result.query_type == "traffic_spike"
        assert "10" in result.interpreted_as

    def test_resilience_check_query(self):
        """Test 'how resilient is the system' query."""
        graph = _build_test_graph()
        engine = NaturalLanguageEngine(graph)

        result = engine.query("How resilient is the system?")

        assert result.query_type == "resilience_check"
        assert "Resilience Score:" in result.answer
        assert "Breakdown:" in result.answer

    def test_resilience_score_query(self):
        """Test 'resilience score' alternative phrasing."""
        graph = _build_test_graph()
        engine = NaturalLanguageEngine(graph)

        result = engine.query("What is the resilience score?")

        assert result.query_type == "resilience_check"

    def test_risk_assessment_query(self):
        """Test 'what are the risks' query."""
        graph = _build_test_graph()
        engine = NaturalLanguageEngine(graph)

        result = engine.query("What are the biggest risks?")

        assert result.query_type == "risk_assessment"
        assert "Risk Assessment" in result.answer

    def test_survival_check_query(self):
        """Test 'can we survive X outage' query."""
        graph = _build_test_graph()
        engine = NaturalLanguageEngine(graph)

        result = engine.query("Can we survive a redis outage?")

        assert result.query_type == "survival_check"
        assert "redis" in result.components_matched
        assert "Survival Check" in result.answer
        assert "Verdict:" in result.answer

    def test_cost_query(self):
        """Test 'what is the cost of an outage' query."""
        graph = _build_test_graph()
        engine = NaturalLanguageEngine(graph)

        result = engine.query("What is the cost of a postgres outage?")

        assert result.query_type == "cost_query"
        assert "postgres" in result.components_matched
        assert "Cost impact" in result.answer or "cost" in result.answer.lower()

    def test_cost_query_system_wide(self):
        """Test system-wide cost query (no component specified)."""
        graph = _build_test_graph()
        engine = NaturalLanguageEngine(graph)

        result = engine.query("What is the cost of a system outage?")

        assert result.query_type == "cost_query"
        assert "System-wide" in result.answer or "$" in result.answer

    def test_availability_query(self):
        """Test 'what is the availability' query."""
        graph = _build_test_graph()
        engine = NaturalLanguageEngine(graph)

        result = engine.query("What is the availability?")

        assert result.query_type == "availability_query"
        assert "Availability" in result.answer

    def test_unknown_query(self):
        """Test handling of unrecognized queries."""
        graph = _build_test_graph()
        engine = NaturalLanguageEngine(graph)

        result = engine.query("Tell me a joke about infrastructure")

        assert result.query_type == "unknown"
        assert "could not understand" in result.answer.lower()

    def test_list_components_query(self):
        """Test 'show components' query."""
        graph = _build_test_graph()
        engine = NaturalLanguageEngine(graph)

        result = engine.query("Show me all the components")

        assert result.query_type == "list_components"
        assert "lb" in result.answer
        assert "app" in result.answer
        assert "postgres" in result.answer

    def test_spof_check_query(self):
        """Test 'single point of failure' query."""
        graph = _build_test_graph()
        engine = NaturalLanguageEngine(graph)

        result = engine.query("What are the single points of failure?")

        assert result.query_type == "spof_check"
        # postgres has 1 replica and no failover, and app depends on it
        assert "postgres" in result.answer.lower() or "PostgreSQL" in result.answer

    def test_cascade_check_query(self):
        """Test 'what cascades' query."""
        graph = _build_test_graph()
        engine = NaturalLanguageEngine(graph)

        result = engine.query("What would cascade through the system?")

        assert result.query_type == "cascade_check"
        assert result.answer != ""

    def test_query_result_structure(self):
        """Test that QueryResult has all expected fields."""
        graph = _build_test_graph()
        engine = NaturalLanguageEngine(graph)

        result = engine.query("How resilient is the system?")

        assert isinstance(result, QueryResult)
        assert isinstance(result.query, str)
        assert isinstance(result.interpreted_as, str)
        assert isinstance(result.answer, str)
        assert isinstance(result.query_type, str)
        assert isinstance(result.components_matched, list)

    def test_empty_graph(self):
        """Test behavior with an empty graph."""
        graph = InfraGraph()
        engine = NaturalLanguageEngine(graph)

        result = engine.query("How resilient is the system?")

        assert result.query_type == "resilience_check"
        assert "0" in result.answer  # Score should be 0

    def test_traffic_multiplier_extraction(self):
        """Test that traffic multipliers are correctly extracted from text."""
        graph = _build_test_graph()
        engine = NaturalLanguageEngine(graph)

        assert engine._extract_traffic_multiplier("10x traffic") == 10.0
        assert engine._extract_traffic_multiplier("double the traffic") == 2.0
        assert engine._extract_traffic_multiplier("triple the load") == 3.0
        assert engine._extract_traffic_multiplier("ddos attack") == 50.0
        assert engine._extract_traffic_multiplier("generic spike") == 5.0  # default

    def test_find_component_fuzzy(self):
        """Test fuzzy component matching."""
        graph = _build_test_graph()
        engine = NaturalLanguageEngine(graph)

        # Exact match
        assert engine._find_component("postgres is down") == "postgres"
        # By name
        assert engine._find_component("Redis Cache failing") == "redis"
        # Substring
        assert engine._find_component("the lb is broken") == "lb"
