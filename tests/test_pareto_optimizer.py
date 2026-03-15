"""Tests for the Pareto Optimizer."""

from __future__ import annotations

import pytest

from infrasim.model.components import (
    AutoScalingConfig,
    CircuitBreakerConfig,
    Component,
    ComponentType,
    Dependency,
    FailoverConfig,
    ResourceMetrics,
)
from infrasim.model.graph import InfraGraph
from infrasim.simulator.pareto_optimizer import (
    COST_PER_REPLICA,
    ParetoFrontier,
    ParetoOptimizer,
    ParetoSolution,
    _calculate_base_cost,
    _count_spofs,
    _score_to_nines,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def simple_graph() -> InfraGraph:
    """Graph with SPOFs: single DB and cache with multiple dependents."""
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
def single_component_graph() -> InfraGraph:
    """Graph with just one component."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="app", name="App Server", type=ComponentType.APP_SERVER,
        replicas=1,
    ))
    return graph


# ---------------------------------------------------------------------------
# Tests: Helper functions
# ---------------------------------------------------------------------------


class TestHelperFunctions:
    """Tests for helper functions."""

    def test_score_to_nines_high(self):
        assert _score_to_nines(99.0) == 5.0

    def test_score_to_nines_medium(self):
        nines = _score_to_nines(75.0)
        assert 2.5 < nines < 4.0

    def test_score_to_nines_low(self):
        nines = _score_to_nines(20.0)
        assert 1.0 < nines < 2.5

    def test_score_to_nines_zero(self):
        nines = _score_to_nines(0.0)
        assert nines >= 0.0

    def test_score_to_nines_monotonic(self):
        """Higher scores should produce higher nines values."""
        prev = -1.0
        for score in range(0, 101, 5):
            nines = _score_to_nines(float(score))
            assert nines >= prev, f"Not monotonic at score={score}"
            prev = nines

    def test_count_spofs_simple(self, simple_graph):
        count = _count_spofs(simple_graph)
        # db and cache have 1 replica and dependents
        assert count >= 1

    def test_count_spofs_redundant(self, redundant_graph):
        count = _count_spofs(redundant_graph)
        assert count == 0

    def test_count_spofs_empty(self, empty_graph):
        count = _count_spofs(empty_graph)
        assert count == 0

    def test_calculate_base_cost(self, simple_graph):
        cost = _calculate_base_cost(simple_graph)
        assert cost > 0
        # lb: 2 * 100 = 200, app: 2 * 200 = 400, db: 1 * 500 = 500, cache: 1 * 150 = 150
        expected = 200 + 400 + 500 + 150
        assert cost == expected

    def test_calculate_base_cost_with_features(self, redundant_graph):
        cost = _calculate_base_cost(redundant_graph)
        # Includes failover costs (100 each) and autoscaling (50 for app)
        assert cost > 0
        # lb: 3*100 + 100 = 400, app: 3*200 + 100 + 50 = 750, db: 2*500 + 100 = 1100
        expected = 400 + 750 + 1100
        assert cost == expected

    def test_calculate_base_cost_empty(self, empty_graph):
        cost = _calculate_base_cost(empty_graph)
        assert cost == 0.0


# ---------------------------------------------------------------------------
# Tests: ParetoOptimizer
# ---------------------------------------------------------------------------


class TestParetoOptimizer:
    """Tests for the ParetoOptimizer class."""

    def test_generate_frontier_empty(self, empty_graph):
        optimizer = ParetoOptimizer()
        frontier = optimizer.generate_frontier(empty_graph)
        assert isinstance(frontier, ParetoFrontier)
        assert len(frontier.solutions) >= 1
        assert frontier.current_solution.is_current

    def test_generate_frontier_simple(self, simple_graph):
        optimizer = ParetoOptimizer()
        frontier = optimizer.generate_frontier(simple_graph)

        assert isinstance(frontier, ParetoFrontier)
        assert len(frontier.solutions) >= 2  # At least current + some improvements

        # Current solution should be included
        current_solutions = [s for s in frontier.solutions if s.is_current]
        assert len(current_solutions) == 1

        # Solutions should be sorted by cost
        costs = [s.estimated_monthly_cost for s in frontier.solutions]
        assert costs == sorted(costs)

    def test_generate_frontier_redundant(self, redundant_graph):
        optimizer = ParetoOptimizer()
        frontier = optimizer.generate_frontier(redundant_graph)
        assert len(frontier.solutions) >= 1
        # Already redundant, so fewer improvement opportunities
        current = frontier.current_solution
        assert current.resilience_score > 0

    def test_frontier_has_current(self, simple_graph):
        optimizer = ParetoOptimizer()
        frontier = optimizer.generate_frontier(simple_graph)
        assert frontier.current_solution is not None
        assert frontier.current_solution.is_current

    def test_frontier_has_cheapest(self, simple_graph):
        optimizer = ParetoOptimizer()
        frontier = optimizer.generate_frontier(simple_graph)
        assert frontier.cheapest_solution is not None
        for s in frontier.solutions:
            assert frontier.cheapest_solution.estimated_monthly_cost <= s.estimated_monthly_cost

    def test_frontier_has_most_resilient(self, simple_graph):
        optimizer = ParetoOptimizer()
        frontier = optimizer.generate_frontier(simple_graph)
        assert frontier.most_resilient_solution is not None
        for s in frontier.solutions:
            assert frontier.most_resilient_solution.resilience_score >= s.resilience_score

    def test_frontier_has_best_value(self, simple_graph):
        optimizer = ParetoOptimizer()
        frontier = optimizer.generate_frontier(simple_graph)
        assert frontier.best_value_solution is not None

    def test_pareto_optimality(self, simple_graph):
        """No solution in the frontier should dominate another."""
        optimizer = ParetoOptimizer()
        frontier = optimizer.generate_frontier(simple_graph)

        for i, sol_a in enumerate(frontier.solutions):
            for j, sol_b in enumerate(frontier.solutions):
                if i == j:
                    continue
                # sol_a should not dominate sol_b
                a_dominates_b = (
                    sol_a.resilience_score >= sol_b.resilience_score
                    and sol_a.estimated_monthly_cost <= sol_b.estimated_monthly_cost
                    and (
                        sol_a.resilience_score > sol_b.resilience_score
                        or sol_a.estimated_monthly_cost < sol_b.estimated_monthly_cost
                    )
                )
                # Allow current solution to be dominated (it's always included)
                if sol_b.is_current:
                    continue
                assert not a_dominates_b, (
                    f"Solution {i} dominates solution {j}: "
                    f"({sol_a.resilience_score}, ${sol_a.estimated_monthly_cost}) vs "
                    f"({sol_b.resilience_score}, ${sol_b.estimated_monthly_cost})"
                )

    def test_solutions_are_deterministic(self, simple_graph):
        """Running twice should produce the same results."""
        optimizer = ParetoOptimizer()
        frontier1 = optimizer.generate_frontier(simple_graph)
        frontier2 = optimizer.generate_frontier(simple_graph)

        assert len(frontier1.solutions) == len(frontier2.solutions)
        for s1, s2 in zip(frontier1.solutions, frontier2.solutions):
            assert s1.resilience_score == s2.resilience_score
            assert s1.estimated_monthly_cost == s2.estimated_monthly_cost

    def test_find_best_for_budget(self, simple_graph):
        optimizer = ParetoOptimizer()
        base_cost = _calculate_base_cost(simple_graph)

        # With a very large budget, should get the most resilient
        solution = optimizer.find_best_for_budget(simple_graph, base_cost * 10)
        assert solution is not None
        assert solution.resilience_score > 0

    def test_find_best_for_budget_tight(self, simple_graph):
        optimizer = ParetoOptimizer()
        base_cost = _calculate_base_cost(simple_graph)

        # With current budget, should get current or near-current
        solution = optimizer.find_best_for_budget(simple_graph, base_cost)
        assert solution is not None
        assert solution.estimated_monthly_cost <= base_cost + 1  # Allow small rounding

    def test_find_cheapest_for_score(self, simple_graph):
        optimizer = ParetoOptimizer()
        current_score = simple_graph.resilience_score()

        # Target current score - should get current or cheaper
        solution = optimizer.find_cheapest_for_score(simple_graph, current_score)
        assert solution is not None
        assert solution.resilience_score >= current_score - 0.1  # Small tolerance

    def test_find_cheapest_for_score_high_target(self, simple_graph):
        optimizer = ParetoOptimizer()
        # Very high target - should get most resilient available
        solution = optimizer.find_cheapest_for_score(simple_graph, 100.0)
        assert solution is not None
        assert solution.resilience_score > 0

    def test_cost_to_improve(self, simple_graph):
        optimizer = ParetoOptimizer()
        cost = optimizer.cost_to_improve(simple_graph, 5.0)
        # Should be >= 0 (might be 0 if free improvements exist like circuit breakers)
        assert cost >= 0.0

    def test_optimize_with_budget(self, simple_graph):
        optimizer = ParetoOptimizer()
        frontier = optimizer.optimize(simple_graph, budget=2000)
        assert isinstance(frontier, ParetoFrontier)
        # All solutions should be within budget
        for s in frontier.solutions:
            assert s.estimated_monthly_cost <= 2000 or s.is_current

    def test_optimize_with_target(self, simple_graph):
        optimizer = ParetoOptimizer()
        frontier = optimizer.optimize(simple_graph, target_score=50.0)
        assert isinstance(frontier, ParetoFrontier)

    def test_single_component(self, single_component_graph):
        optimizer = ParetoOptimizer()
        frontier = optimizer.generate_frontier(single_component_graph)
        assert len(frontier.solutions) >= 1
        assert frontier.current_solution.is_current


# ---------------------------------------------------------------------------
# Tests: ParetoSolution
# ---------------------------------------------------------------------------


class TestParetoSolution:
    """Tests for ParetoSolution data class."""

    def test_solution_fields(self):
        sol = ParetoSolution(
            variables={"app": {"replicas": 3}},
            resilience_score=85.0,
            estimated_monthly_cost=1500.0,
            availability_nines=3.5,
            spof_count=1,
            is_current=False,
            improvements_from_current=["App Server: replicas 1 -> 3"],
        )
        assert sol.resilience_score == 85.0
        assert sol.estimated_monthly_cost == 1500.0
        assert sol.availability_nines == 3.5
        assert sol.spof_count == 1
        assert not sol.is_current
        assert len(sol.improvements_from_current) == 1

    def test_current_solution(self):
        sol = ParetoSolution(
            variables={},
            resilience_score=70.0,
            estimated_monthly_cost=1000.0,
            availability_nines=3.0,
            spof_count=2,
            is_current=True,
        )
        assert sol.is_current
        assert len(sol.improvements_from_current) == 0


# ---------------------------------------------------------------------------
# Tests: Cost calculations
# ---------------------------------------------------------------------------


class TestCostCalculations:
    """Tests for cost estimation logic."""

    def test_cost_per_replica_defined_for_all_types(self):
        """All component types in the enum should have a cost per replica."""
        for comp_type in ComponentType:
            assert comp_type in COST_PER_REPLICA, f"Missing cost for {comp_type.value}"

    def test_external_api_free(self):
        """External APIs should have $0 cost per replica."""
        assert COST_PER_REPLICA[ComponentType.EXTERNAL_API] == 0.0

    def test_database_most_expensive(self):
        """Databases should be the most expensive per replica."""
        db_cost = COST_PER_REPLICA[ComponentType.DATABASE]
        for comp_type, cost in COST_PER_REPLICA.items():
            assert db_cost >= cost, f"DB cost ({db_cost}) < {comp_type.value} cost ({cost})"

    def test_improvements_described(self, simple_graph):
        """Changes from current should produce human-readable descriptions."""
        optimizer = ParetoOptimizer()
        frontier = optimizer.generate_frontier(simple_graph)

        non_current = [s for s in frontier.solutions if not s.is_current]
        if non_current:
            sol = non_current[0]
            # Non-current solutions should have at least one improvement
            assert len(sol.improvements_from_current) >= 1
            # Improvements should be readable strings
            for imp in sol.improvements_from_current:
                assert isinstance(imp, str)
                assert len(imp) > 0
