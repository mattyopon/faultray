"""Tests for Monte Carlo availability simulation."""

from __future__ import annotations

import math

import pytest

from faultray.model.components import (
    Component,
    ComponentType,
    Dependency,
    OperationalProfile,
)
from faultray.model.graph import InfraGraph
from faultray.simulator.monte_carlo import MonteCarloResult, run_monte_carlo


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _simple_graph() -> InfraGraph:
    """Build a simple 3-component graph: LB -> App -> DB."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="lb", name="LB", type=ComponentType.LOAD_BALANCER, replicas=2,
        operational_profile=OperationalProfile(mtbf_hours=8760, mttr_minutes=2),
    ))
    graph.add_component(Component(
        id="app", name="App", type=ComponentType.APP_SERVER, replicas=3,
        operational_profile=OperationalProfile(mtbf_hours=2160, mttr_minutes=5),
    ))
    graph.add_component(Component(
        id="db", name="DB", type=ComponentType.DATABASE, replicas=1,
        operational_profile=OperationalProfile(mtbf_hours=4320, mttr_minutes=30),
    ))
    graph.add_dependency(Dependency(
        source_id="lb", target_id="app", dependency_type="requires",
    ))
    graph.add_dependency(Dependency(
        source_id="app", target_id="db", dependency_type="requires",
    ))
    return graph


def _high_reliability_graph() -> InfraGraph:
    """Single highly reliable component (very high MTBF, very low MTTR)."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="reliable", name="Reliable", type=ComponentType.APP_SERVER,
        replicas=3,
        operational_profile=OperationalProfile(mtbf_hours=87600, mttr_minutes=1),
    ))
    return graph


def _spof_graph() -> InfraGraph:
    """Single point of failure: 1-replica DB with short MTBF."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="db", name="DB", type=ComponentType.DATABASE,
        replicas=1,
        operational_profile=OperationalProfile(mtbf_hours=500, mttr_minutes=60),
    ))
    return graph


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestReproducibility:
    """Deterministic seed should give reproducible results."""

    def test_same_seed_same_results(self) -> None:
        graph = _simple_graph()
        r1 = run_monte_carlo(graph, n_trials=500, seed=12345)
        r2 = run_monte_carlo(graph, n_trials=500, seed=12345)
        assert r1.availability_mean == r2.availability_mean
        assert r1.availability_p50 == r2.availability_p50
        assert r1.availability_p95 == r2.availability_p95
        assert r1.trial_results == r2.trial_results

    def test_different_seed_different_results(self) -> None:
        graph = _simple_graph()
        r1 = run_monte_carlo(graph, n_trials=500, seed=1)
        r2 = run_monte_carlo(graph, n_trials=500, seed=999)
        # Extremely unlikely to be exactly the same with different seeds
        assert r1.availability_mean != r2.availability_mean


class TestHighReliability:
    """High-reliability components should produce high availability."""

    def test_high_reliability_gives_high_availability(self) -> None:
        graph = _high_reliability_graph()
        result = run_monte_carlo(graph, n_trials=1000, seed=42)
        # 3 replicas with MTBF=87600h, MTTR=1min => very high availability
        assert result.availability_mean > 0.999, (
            f"Mean availability {result.availability_mean} should be > 99.9%"
        )
        assert result.availability_p50 > 0.999
        assert result.availability_p95 > 0.999


class TestSPOF:
    """Single point of failure should give lower availability."""

    def test_spof_gives_lower_availability(self) -> None:
        graph_spof = _spof_graph()
        graph_reliable = _high_reliability_graph()
        r_spof = run_monte_carlo(graph_spof, n_trials=1000, seed=42)
        r_reliable = run_monte_carlo(graph_reliable, n_trials=1000, seed=42)
        assert r_spof.availability_mean < r_reliable.availability_mean, (
            f"SPOF mean {r_spof.availability_mean} should be < "
            f"reliable mean {r_reliable.availability_mean}"
        )

    def test_spof_downtime_is_significant(self) -> None:
        graph = _spof_graph()
        result = run_monte_carlo(graph, n_trials=1000, seed=42)
        # MTBF=500h, MTTR=60min with 1 replica should have noticeable downtime
        assert result.annual_downtime_p50_seconds > 0


class TestConfidenceInterval:
    """Confidence interval should contain the mean."""

    def test_ci_contains_mean(self) -> None:
        graph = _simple_graph()
        result = run_monte_carlo(graph, n_trials=5000, seed=42)
        ci_lower, ci_upper = result.confidence_interval_95
        assert ci_lower <= result.availability_mean <= ci_upper, (
            f"95% CI [{ci_lower}, {ci_upper}] should contain "
            f"mean {result.availability_mean}"
        )

    def test_ci_is_valid_range(self) -> None:
        graph = _simple_graph()
        result = run_monte_carlo(graph, n_trials=1000, seed=42)
        ci_lower, ci_upper = result.confidence_interval_95
        assert ci_lower < ci_upper, "CI lower should be < upper"
        assert ci_lower >= 0.0, "CI lower should be >= 0"


class TestTrialCount:
    """More trials should give tighter confidence intervals."""

    def test_more_trials_tighter_ci(self) -> None:
        graph = _simple_graph()
        r_few = run_monte_carlo(graph, n_trials=100, seed=42)
        r_many = run_monte_carlo(graph, n_trials=10000, seed=42)

        ci_width_few = r_few.confidence_interval_95[1] - r_few.confidence_interval_95[0]
        ci_width_many = r_many.confidence_interval_95[1] - r_many.confidence_interval_95[0]

        assert ci_width_many < ci_width_few, (
            f"CI width with 10000 trials ({ci_width_many}) should be < "
            f"CI width with 100 trials ({ci_width_few})"
        )

    def test_trial_results_count_matches_n_trials(self) -> None:
        graph = _simple_graph()
        result = run_monte_carlo(graph, n_trials=200, seed=42)
        assert len(result.trial_results) == 200


class TestEmptyGraph:
    """Empty graph should return zero availability."""

    def test_empty_graph_zero_availability(self) -> None:
        graph = InfraGraph()
        result = run_monte_carlo(graph, n_trials=100, seed=42)
        assert result.availability_mean == 0.0
        assert result.availability_p50 == 0.0
        assert result.availability_p95 == 0.0
        assert result.availability_p99 == 0.0
        assert result.n_trials == 100
        assert len(result.trial_results) == 0

    def test_empty_graph_max_downtime(self) -> None:
        graph = InfraGraph()
        result = run_monte_carlo(graph, n_trials=100, seed=42)
        seconds_per_year = 365.25 * 24 * 3600
        assert result.annual_downtime_p50_seconds == seconds_per_year


class TestResultStructure:
    """Verify the result dataclass fields."""

    def test_result_fields(self) -> None:
        graph = _simple_graph()
        result = run_monte_carlo(graph, n_trials=100, seed=42)
        assert isinstance(result, MonteCarloResult)
        assert isinstance(result.n_trials, int)
        assert isinstance(result.availability_p50, float)
        assert isinstance(result.availability_p95, float)
        assert isinstance(result.availability_p99, float)
        assert isinstance(result.availability_mean, float)
        assert isinstance(result.availability_std, float)
        assert isinstance(result.annual_downtime_p50_seconds, float)
        assert isinstance(result.annual_downtime_p95_seconds, float)
        assert isinstance(result.confidence_interval_95, tuple)
        assert len(result.confidence_interval_95) == 2
        assert isinstance(result.trial_results, list)

    def test_availability_values_in_range(self) -> None:
        graph = _simple_graph()
        result = run_monte_carlo(graph, n_trials=500, seed=42)
        assert 0.0 <= result.availability_mean <= 1.0
        assert 0.0 <= result.availability_p50 <= 1.0
        assert 0.0 <= result.availability_p95 <= 1.0
        assert 0.0 <= result.availability_p99 <= 1.0
        assert result.availability_std >= 0.0

    def test_percentile_ordering(self) -> None:
        """p50 <= p95 <= p99 for availability."""
        graph = _simple_graph()
        result = run_monte_carlo(graph, n_trials=2000, seed=42)
        assert result.availability_p50 <= result.availability_p95
        assert result.availability_p95 <= result.availability_p99

    def test_downtime_is_non_negative(self) -> None:
        graph = _simple_graph()
        result = run_monte_carlo(graph, n_trials=100, seed=42)
        assert result.annual_downtime_p50_seconds >= 0
        assert result.annual_downtime_p95_seconds >= 0


class TestReplicasEffect:
    """More replicas should increase simulated availability."""

    def test_more_replicas_higher_availability(self) -> None:
        graph1 = InfraGraph()
        graph1.add_component(Component(
            id="app", name="App", type=ComponentType.APP_SERVER, replicas=1,
            operational_profile=OperationalProfile(mtbf_hours=2160, mttr_minutes=30),
        ))

        graph3 = InfraGraph()
        graph3.add_component(Component(
            id="app", name="App", type=ComponentType.APP_SERVER, replicas=3,
            operational_profile=OperationalProfile(mtbf_hours=2160, mttr_minutes=30),
        ))

        r1 = run_monte_carlo(graph1, n_trials=2000, seed=42)
        r3 = run_monte_carlo(graph3, n_trials=2000, seed=42)

        assert r3.availability_mean > r1.availability_mean, (
            f"3-replica mean {r3.availability_mean} should be > "
            f"1-replica mean {r1.availability_mean}"
        )


class TestHelpers:
    """Test internal helper functions."""

    def test_percentile_empty_list(self) -> None:
        from faultray.simulator.monte_carlo import _percentile
        assert _percentile([], 50) == 0.0

    def test_percentile_single_element(self) -> None:
        from faultray.simulator.monte_carlo import _percentile
        assert _percentile([42.0], 50) == 42.0
        assert _percentile([42.0], 0) == 42.0
        assert _percentile([42.0], 100) == 42.0

    def test_percentile_exact_index(self) -> None:
        from faultray.simulator.monte_carlo import _percentile
        # 3 elements: indices 0, 1, 2. p50 -> k = 0.5 * 2 = 1.0 (exact)
        assert _percentile([1.0, 2.0, 3.0], 50) == 2.0

    def test_mean_empty(self) -> None:
        from faultray.simulator.monte_carlo import _mean
        assert _mean([]) == 0.0

    def test_std_empty_and_single(self) -> None:
        from faultray.simulator.monte_carlo import _std
        assert _std([]) == 0.0
        assert _std([5.0]) == 0.0

    def test_sample_exponential_zero_mean(self) -> None:
        import random as rand_mod
        from faultray.simulator.monte_carlo import _sample_exponential
        rng = rand_mod.Random(42)
        assert _sample_exponential(rng, 0.0) == 0.0

    def test_sample_lognormal_zero_mean(self) -> None:
        import random as rand_mod
        from faultray.simulator.monte_carlo import _sample_lognormal
        rng = rand_mod.Random(42)
        assert _sample_lognormal(rng, 0.0) == 0.0


class TestDefaultMTBF:
    """Test default MTBF/MTTR handling for components with zero values."""

    def test_zero_mtbf_uses_default(self) -> None:
        """Components with zero MTBF should use type-based defaults."""
        graph = InfraGraph()
        graph.add_component(Component(
            id="app", name="App", type=ComponentType.APP_SERVER, replicas=1,
            operational_profile=OperationalProfile(mtbf_hours=0, mttr_minutes=0),
        ))
        result = run_monte_carlo(graph, n_trials=100, seed=42)
        # Should still produce valid results (not crash)
        assert 0.0 <= result.availability_mean <= 1.0

    def test_non_critical_path_component(self) -> None:
        """Components with 'optional' dependencies are not on the critical path."""
        graph = InfraGraph()
        graph.add_component(Component(
            id="app", name="App", type=ComponentType.APP_SERVER, replicas=1,
            operational_profile=OperationalProfile(mtbf_hours=2160, mttr_minutes=5),
        ))
        graph.add_component(Component(
            id="cache", name="Cache", type=ComponentType.CACHE, replicas=1,
            operational_profile=OperationalProfile(mtbf_hours=500, mttr_minutes=30),
        ))
        graph.add_dependency(Dependency(
            source_id="app", target_id="cache", dependency_type="optional",
        ))
        # Cache is optional, so its failures shouldn't affect system availability
        result = run_monte_carlo(graph, n_trials=1000, seed=42)
        # App alone is on critical path, availability should be reasonable
        assert result.availability_mean > 0.9
