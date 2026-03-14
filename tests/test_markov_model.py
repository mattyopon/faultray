"""Tests for the Markov chain availability model."""

from __future__ import annotations

import math

import pytest

from infrasim.model.components import (
    Component,
    ComponentType,
    DegradationConfig,
    Dependency,
    OperationalProfile,
)
from infrasim.model.graph import InfraGraph
from infrasim.simulator.markov_model import (
    MarkovResult,
    _build_transition_matrix,
    _normalize,
    _solve_steady_state,
    _vec_mat_mul,
    compute_markov_availability,
    compute_system_markov,
)


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


# ---------------------------------------------------------------------------
# Tests for matrix helpers
# ---------------------------------------------------------------------------


class TestMatrixHelpers:
    """Tests for manual matrix operation helpers."""

    def test_normalize(self) -> None:
        result = _normalize([2.0, 3.0, 5.0])
        assert abs(sum(result) - 1.0) < 1e-10
        assert abs(result[0] - 0.2) < 1e-10
        assert abs(result[1] - 0.3) < 1e-10
        assert abs(result[2] - 0.5) < 1e-10

    def test_normalize_zeros(self) -> None:
        result = _normalize([0.0, 0.0, 0.0])
        assert abs(sum(result) - 1.0) < 1e-10

    def test_vec_mat_mul_identity(self) -> None:
        identity = [[1, 0, 0], [0, 1, 0], [0, 0, 1]]
        vec = [0.5, 0.3, 0.2]
        result = _vec_mat_mul(vec, identity)
        for i in range(3):
            assert abs(result[i] - vec[i]) < 1e-10


class TestTransitionMatrix:
    """Tests for transition matrix construction."""

    def test_rows_sum_to_one(self) -> None:
        matrix = _build_transition_matrix(
            mtbf_hours=2000, mttr_hours=0.5,
            degradation_rate=0.01, recovery_from_degraded_rate=0.1,
        )
        for row in matrix:
            assert abs(sum(row) - 1.0) < 1e-10, f"Row sums to {sum(row)}, not 1.0"

    def test_all_probabilities_non_negative(self) -> None:
        matrix = _build_transition_matrix(
            mtbf_hours=1000, mttr_hours=1.0,
            degradation_rate=0.05, recovery_from_degraded_rate=0.2,
        )
        for row in matrix:
            for val in row:
                assert val >= 0, f"Negative probability: {val}"

    def test_high_mtbf_mostly_healthy(self) -> None:
        matrix = _build_transition_matrix(
            mtbf_hours=100000, mttr_hours=0.01,
            degradation_rate=0.001, recovery_from_degraded_rate=0.5,
        )
        # With very high MTBF, P(stay healthy) should be very high
        assert matrix[0][0] > 0.99


# ---------------------------------------------------------------------------
# Tests for steady-state solver
# ---------------------------------------------------------------------------


class TestSteadyStateSolver:
    """Tests for the power-method steady-state solver."""

    def test_identity_matrix_uniform(self) -> None:
        # Identity matrix: any distribution is steady state;
        # power method should converge to the initial uniform guess
        identity = [[1, 0, 0], [0, 1, 0], [0, 0, 1]]
        pi = _solve_steady_state(identity)
        # Each element should be 1/3 since we start uniform
        for v in pi:
            assert abs(v - 1.0 / 3.0) < 1e-6

    def test_absorbing_state(self) -> None:
        # All transitions go to state 2
        matrix = [
            [0.0, 0.0, 1.0],
            [0.0, 0.0, 1.0],
            [0.0, 0.0, 1.0],
        ]
        pi = _solve_steady_state(matrix)
        assert pi[2] > 0.99
        assert abs(pi[0]) < 1e-6

    def test_steady_state_sums_to_one(self) -> None:
        matrix = _build_transition_matrix(
            mtbf_hours=2000, mttr_hours=0.5,
            degradation_rate=0.01, recovery_from_degraded_rate=0.1,
        )
        pi = _solve_steady_state(matrix)
        assert abs(sum(pi) - 1.0) < 1e-8


# ---------------------------------------------------------------------------
# Tests for compute_markov_availability
# ---------------------------------------------------------------------------


class TestComputeMarkovAvailability:
    """Tests for the main Markov availability computation."""

    def test_result_structure(self) -> None:
        result = compute_markov_availability(
            mtbf_hours=2160, mttr_hours=0.5,
        )
        assert isinstance(result, MarkovResult)
        assert "HEALTHY" in result.steady_state
        assert "DEGRADED" in result.steady_state
        assert "DOWN" in result.steady_state
        assert 0.0 <= result.availability <= 1.0
        assert result.nines >= 0
        assert len(result.transition_matrix) == 3

    def test_high_mtbf_high_availability(self) -> None:
        result = compute_markov_availability(
            mtbf_hours=87600, mttr_hours=0.1,
        )
        assert result.availability > 0.99
        assert result.nines >= 2.0

    def test_low_mtbf_lower_availability(self) -> None:
        result_high = compute_markov_availability(
            mtbf_hours=87600, mttr_hours=0.5,
        )
        result_low = compute_markov_availability(
            mtbf_hours=100, mttr_hours=0.5,
        )
        assert result_low.availability < result_high.availability

    def test_longer_mttr_lower_availability(self) -> None:
        result_short = compute_markov_availability(
            mtbf_hours=2160, mttr_hours=0.1,
        )
        result_long = compute_markov_availability(
            mtbf_hours=2160, mttr_hours=10.0,
        )
        assert result_long.availability < result_short.availability

    def test_steady_state_sums_to_one(self) -> None:
        result = compute_markov_availability(
            mtbf_hours=2160, mttr_hours=0.5,
        )
        total = sum(result.steady_state.values())
        assert abs(total - 1.0) < 1e-6

    def test_availability_equals_healthy_plus_degraded(self) -> None:
        result = compute_markov_availability(
            mtbf_hours=4320, mttr_hours=0.5,
        )
        expected = result.steady_state["HEALTHY"] + result.steady_state["DEGRADED"]
        assert abs(result.availability - expected) < 1e-6

    def test_nines_calculation(self) -> None:
        result = compute_markov_availability(
            mtbf_hours=87600, mttr_hours=0.01,
        )
        if result.availability < 1.0:
            expected_nines = -math.log10(1.0 - result.availability)
            assert abs(result.nines - round(expected_nines, 4)) < 0.01

    def test_mean_time_in_state(self) -> None:
        result = compute_markov_availability(
            mtbf_hours=2160, mttr_hours=0.5,
        )
        assert "HEALTHY" in result.mean_time_in_state
        assert "DEGRADED" in result.mean_time_in_state
        assert "DOWN" in result.mean_time_in_state
        # Mean time in HEALTHY should be > mean time in DOWN
        assert result.mean_time_in_state["HEALTHY"] >= result.mean_time_in_state["DOWN"]


# ---------------------------------------------------------------------------
# Tests for compute_system_markov
# ---------------------------------------------------------------------------


class TestSystemMarkov:
    """Tests for system-wide Markov analysis."""

    def test_all_components_analyzed(self) -> None:
        graph = _simple_graph()
        results = compute_system_markov(graph)
        assert set(results.keys()) == {"lb", "app", "db"}

    def test_empty_graph(self) -> None:
        graph = InfraGraph()
        results = compute_system_markov(graph)
        assert len(results) == 0

    def test_degradation_increases_degradation_rate(self) -> None:
        """Components with degradation should use higher degradation rate."""
        graph = InfraGraph()
        graph.add_component(Component(
            id="leaky", name="Leaky App", type=ComponentType.APP_SERVER,
            replicas=1,
            operational_profile=OperationalProfile(
                mtbf_hours=2160, mttr_minutes=10,
                degradation=DegradationConfig(memory_leak_mb_per_hour=50),
            ),
        ))
        graph.add_component(Component(
            id="clean", name="Clean App", type=ComponentType.APP_SERVER,
            replicas=1,
            operational_profile=OperationalProfile(
                mtbf_hours=2160, mttr_minutes=10,
            ),
        ))

        results = compute_system_markov(graph)
        # Leaky component should have higher P(DEGRADED)
        leaky = results["leaky"]
        clean = results["clean"]
        assert leaky.steady_state["DEGRADED"] > clean.steady_state["DEGRADED"]
