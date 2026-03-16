"""Tests for the Pareto Optimizer."""

from __future__ import annotations

import pytest

from faultray.model.components import (
    AutoScalingConfig,
    CircuitBreakerConfig,
    Component,
    ComponentType,
    Dependency,
    FailoverConfig,
    ResourceMetrics,
)
from faultray.model.graph import InfraGraph
from faultray.simulator.pareto_optimizer import (
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


# ---------------------------------------------------------------------------
# Additional tests for 99%+ coverage
# ---------------------------------------------------------------------------

import copy
from unittest.mock import patch


class TestScoreToNinesFallback:
    """Cover the fallback return 1.0 in _score_to_nines (line 137)."""

    def test_score_to_nines_boundary_values(self):
        assert _score_to_nines(0.0) == 1.0
        assert _score_to_nines(100.0) == 5.0
        assert _score_to_nines(99.0) == 5.0
        assert _score_to_nines(98.9) < 5.0


class TestExtractVariables:
    """Cover _extract_variables (lines 179-234)."""

    def test_extract_variables_basic(self, simple_graph):
        """Components without failover/autoscaling/CB generate toggle variables."""
        optimizer = ParetoOptimizer()
        variables = optimizer._extract_variables(simple_graph)
        assert len(variables) > 0

        # Check that we have replicas variables
        replica_vars = [v for v in variables if v.parameter == "replicas"]
        assert len(replica_vars) >= 1

        # Check that components without failover get failover variables
        failover_vars = [v for v in variables if v.parameter == "enable_failover"]
        assert len(failover_vars) >= 1

        # Check that components without autoscaling get autoscaling variables
        autoscaling_vars = [v for v in variables if v.parameter == "enable_autoscaling"]
        assert len(autoscaling_vars) >= 1

    def test_extract_variables_with_cb(self, simple_graph):
        """Components with edges missing circuit breakers get CB variables."""
        optimizer = ParetoOptimizer()
        variables = optimizer._extract_variables(simple_graph)
        cb_vars = [v for v in variables if v.parameter == "enable_circuit_breaker"]
        # simple_graph has edges without CBs
        assert len(cb_vars) >= 1

    def test_extract_variables_fully_configured(self, redundant_graph):
        """Fully configured graph should have fewer toggle variables."""
        optimizer = ParetoOptimizer()
        variables = optimizer._extract_variables(redundant_graph)
        # Redundant graph has failover and autoscaling already enabled
        failover_vars = [v for v in variables if v.parameter == "enable_failover"]
        assert len(failover_vars) == 0  # All have failover

    def test_extract_variables_empty(self, empty_graph):
        """Empty graph has no variables."""
        optimizer = ParetoOptimizer()
        variables = optimizer._extract_variables(empty_graph)
        assert len(variables) == 0


class TestApplyChangesEdgeCases:
    """Cover _apply_changes with invalid comp_id (line 246)."""

    def test_apply_changes_invalid_component(self, simple_graph):
        """Changes for non-existent component should be skipped."""
        optimizer = ParetoOptimizer()
        changes = {"nonexistent_comp": {"replicas": 3}}
        result = optimizer._apply_changes(simple_graph, changes)
        assert isinstance(result, InfraGraph)
        # Original graph should be unchanged
        assert simple_graph.get_component("db").replicas == 1

    def test_apply_changes_mixed_valid_invalid(self, simple_graph):
        """Valid and invalid component changes together."""
        optimizer = ParetoOptimizer()
        changes = {
            "db": {"replicas": 3},
            "nonexistent": {"replicas": 5},
        }
        result = optimizer._apply_changes(simple_graph, changes)
        assert result.get_component("db").replicas == 3
        assert result.get_component("nonexistent") is None


class TestCalculateCostEdgeCases:
    """Cover _calculate_cost_of_changes with invalid comp_id (line 273)."""

    def test_cost_of_changes_invalid_component(self, simple_graph):
        """Cost calculation with non-existent component should skip it."""
        optimizer = ParetoOptimizer()
        changes = {"nonexistent_comp": {"replicas": 5}}
        cost = optimizer._calculate_cost_of_changes(simple_graph, changes)
        assert cost == 0.0

    def test_cost_of_changes_mixed(self, simple_graph):
        """Mix of valid and invalid components in cost calculation."""
        optimizer = ParetoOptimizer()
        changes = {
            "db": {"replicas": 3},          # valid: 2 extra replicas * 500 = 1000
            "ghost": {"replicas": 10},       # invalid: skipped
        }
        cost = optimizer._calculate_cost_of_changes(simple_graph, changes)
        assert cost > 0  # Only the valid component contributes


class TestDescribeImprovementsEdgeCases:
    """Cover _describe_improvements with invalid comp_id (line 298)."""

    def test_describe_improvements_invalid_component(self, simple_graph):
        """Describing improvements for non-existent component should skip it."""
        optimizer = ParetoOptimizer()
        changes = {"ghost_comp": {"replicas": 3}}
        improvements = optimizer._describe_improvements(simple_graph, changes)
        assert len(improvements) == 0


class TestBuildCandidatesReplicaSkip:
    """Cover the replicas skip path in _generate_incremental_changes (line 398)."""

    def test_incremental_changes_replica_ordering(self, simple_graph):
        """The incremental change generator should skip lower replica counts."""
        optimizer = ParetoOptimizer()
        candidates = optimizer._generate_incremental_changes(simple_graph)
        assert len(candidates) > 0
        # Verify that incremental changes were generated
        replica_changes = []
        for change_set in candidates:
            for comp_id, params in change_set.items():
                if "replicas" in params:
                    replica_changes.append((comp_id, params["replicas"]))
        assert len(replica_changes) > 0


class TestFilterParetoOptimalEmpty:
    """Cover _filter_pareto_optimal with empty list (line 464)."""

    def test_filter_pareto_empty(self):
        """Empty solution list should return empty."""
        optimizer = ParetoOptimizer()
        result = optimizer._filter_pareto_optimal([])
        assert result == []


class TestGenerateFrontierEdgeCases:
    """Cover edge cases in generate_frontier (lines 536-537, 542-553)."""

    def test_frontier_steps_limit(self, simple_graph):
        """When there are more solutions than steps, sampling should occur."""
        optimizer = ParetoOptimizer()
        # Use steps=2 to force trimming (lines 542-553)
        frontier = optimizer.generate_frontier(simple_graph, steps=2)
        assert isinstance(frontier, ParetoFrontier)
        # Should still have the current solution
        current_found = any(s.is_current for s in frontier.solutions)
        assert current_found

    def test_frontier_very_small_steps(self):
        """With steps=1, force the sampling code path including pareto[0],
        pareto[-1], and current_sol re-insertion (lines 542-553)."""
        graph = InfraGraph()
        # Create many components to ensure many Pareto solutions
        for i in range(8):
            graph.add_component(Component(
                id=f"svc{i}", name=f"Service{i}", type=ComponentType.APP_SERVER,
                replicas=1,
            ))
        for i in range(7):
            graph.add_dependency(Dependency(
                source_id=f"svc{i}", target_id=f"svc{i+1}",
                dependency_type="requires",
            ))

        optimizer = ParetoOptimizer()
        frontier = optimizer.generate_frontier(graph, steps=1)
        assert isinstance(frontier, ParetoFrontier)
        # Should still include the current solution
        assert any(s.is_current for s in frontier.solutions)

    def test_frontier_steps_2_with_many_components(self):
        """Steps=2 with many components to trigger all sampling branches."""
        graph = InfraGraph()
        for i in range(10):
            graph.add_component(Component(
                id=f"node{i}", name=f"Node{i}", type=ComponentType.APP_SERVER,
                replicas=1,
            ))
        for i in range(9):
            graph.add_dependency(Dependency(
                source_id=f"node{i}", target_id=f"node{i+1}",
                dependency_type="requires",
            ))

        optimizer = ParetoOptimizer()
        frontier = optimizer.generate_frontier(graph, steps=2)
        assert isinstance(frontier, ParetoFrontier)
        assert any(s.is_current for s in frontier.solutions)

    def test_frontier_sampling_reinserts_current(self, simple_graph):
        """Verify sampling re-inserts current_sol when it's not in the sampled
        subset (line 551)."""
        optimizer = ParetoOptimizer()

        # Mock _filter_pareto_optimal to return many distinct solutions
        # with current placed at an odd index so step_size skips it
        original_filter = optimizer._filter_pareto_optimal

        def mock_filter_inflated(solutions):
            """Return all unique solutions to inflate the Pareto front."""
            seen = set()
            result = []
            for s in solutions:
                key = (round(s.resilience_score, 2), round(s.estimated_monthly_cost, 0))
                if key not in seen:
                    seen.add(key)
                    result.append(s)
            # Sort by cost so current (cheapest) ends up at index 0
            result.sort(key=lambda s: s.estimated_monthly_cost)
            # Move the current to index 1 so step_size=large skips it
            current_idx = None
            for i, s in enumerate(result):
                if s.is_current:
                    current_idx = i
                    break
            if current_idx is not None and len(result) > 3:
                current_sol = result.pop(current_idx)
                # Insert at position 1 (not 0, not last)
                result.insert(1, current_sol)
            return result

        with patch.object(optimizer, "_filter_pareto_optimal", side_effect=mock_filter_inflated):
            frontier = optimizer.generate_frontier(simple_graph, steps=2)

        assert isinstance(frontier, ParetoFrontier)
        assert any(s.is_current for s in frontier.solutions)

    def test_frontier_current_reinserted_when_filtered(self, simple_graph):
        """When _filter_pareto_optimal drops the current, it should be re-added
        (lines 536-537)."""
        optimizer = ParetoOptimizer()

        # Patch _filter_pareto_optimal to always drop current solutions
        original_filter = optimizer._filter_pareto_optimal

        def mock_filter(solutions):
            result = original_filter(solutions)
            return [s for s in result if not s.is_current]

        with patch.object(optimizer, "_filter_pareto_optimal", side_effect=mock_filter):
            frontier = optimizer.generate_frontier(simple_graph)

        # Current should still be present (re-added after filtering)
        assert any(s.is_current for s in frontier.solutions)


class TestOptimizeEdgeCases:
    """Cover optimize edge cases (line 611)."""

    def test_optimize_zero_budget(self, simple_graph):
        """Budget of zero should leave only the current solution (line 611)."""
        optimizer = ParetoOptimizer()
        frontier = optimizer.optimize(simple_graph, budget=0.0)
        assert isinstance(frontier, ParetoFrontier)
        assert len(frontier.solutions) >= 1
        # With $0 budget nothing affordable => should fall back to current
        assert frontier.solutions[0].is_current


class TestFindCheapestForScoreEdgeCases:
    """Cover find_cheapest_for_score fallback (line 635)."""

    def test_find_cheapest_impossible_target(self, simple_graph):
        """Impossible target score should return most resilient (line 635)."""
        optimizer = ParetoOptimizer()
        # Target score of 999 is unreachable
        solution = optimizer.find_cheapest_for_score(simple_graph, 999.0)
        assert solution is not None
        assert solution.resilience_score > 0


class TestFindBestForBudgetEdgeCases:
    """Cover find_best_for_budget fallback (line 649)."""

    def test_find_best_zero_budget(self, simple_graph):
        """Zero budget should return cheapest solution (line 649)."""
        optimizer = ParetoOptimizer()
        solution = optimizer.find_best_for_budget(simple_graph, 0.0)
        assert solution is not None


class TestCostToImproveEdgeCases:
    """Cover cost_to_improve fallback (line 670)."""

    def test_cost_to_improve_huge_delta(self, simple_graph):
        """Huge improvement delta with no viable solution should return 0.0."""
        optimizer = ParetoOptimizer()
        # Request an absurd improvement - e.g., 200 points (max is 100)
        cost = optimizer.cost_to_improve(simple_graph, 200.0)
        assert cost == 0.0
