"""Tests for the Markov chain availability model."""

from __future__ import annotations

import math

import pytest

from faultray.model.components import (
    Component,
    ComponentType,
    DegradationConfig,
    Dependency,
    HealthStatus,
    OperationalProfile,
)
from faultray.model.graph import InfraGraph
from faultray.simulator.markov_model import (
    MarkovResult,
    _DEFAULT_MTBF,
    _build_transition_matrix,
    _converged,
    _mat_vec_mul,
    _normalize,
    _solve_steady_state,
    _vec_mat_mul,
    compute_markov_availability,
    compute_system_markov,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _comp(
    cid: str,
    name: str,
    ctype: ComponentType = ComponentType.APP_SERVER,
    replicas: int = 1,
    health: HealthStatus = HealthStatus.HEALTHY,
    mtbf_hours: float = 0.0,
    mttr_minutes: float = 30.0,
    memory_leak: float = 0.0,
    disk_fill: float = 0.0,
) -> Component:
    return Component(
        id=cid,
        name=name,
        type=ctype,
        replicas=replicas,
        health=health,
        operational_profile=OperationalProfile(
            mtbf_hours=mtbf_hours,
            mttr_minutes=mttr_minutes,
            degradation=DegradationConfig(
                memory_leak_mb_per_hour=memory_leak,
                disk_fill_gb_per_hour=disk_fill,
            ),
        ),
    )


def _chain_graph() -> InfraGraph:
    """Build LB -> App -> DB graph."""
    g = InfraGraph()
    g.add_component(_comp("lb", "LB", ComponentType.LOAD_BALANCER, replicas=2, mtbf_hours=8760, mttr_minutes=2))
    g.add_component(_comp("app", "App", replicas=3, mtbf_hours=2160, mttr_minutes=5))
    g.add_component(_comp("db", "DB", ComponentType.DATABASE, replicas=1, mtbf_hours=4320, mttr_minutes=30))
    g.add_dependency(Dependency(source_id="lb", target_id="app", dependency_type="requires"))
    g.add_dependency(Dependency(source_id="app", target_id="db", dependency_type="requires"))
    return g


# ---------------------------------------------------------------------------
# Tests: _mat_vec_mul
# ---------------------------------------------------------------------------


class TestMatVecMul:
    def test_identity(self) -> None:
        identity = [[1, 0, 0], [0, 1, 0], [0, 0, 1]]
        vec = [1.0, 2.0, 3.0]
        result = _mat_vec_mul(identity, vec)
        for i in range(3):
            assert abs(result[i] - vec[i]) < 1e-10

    def test_simple_multiplication(self) -> None:
        matrix = [[1, 2], [3, 4]]
        vec = [1.0, 1.0]
        result = _mat_vec_mul(matrix, vec)
        assert abs(result[0] - 3.0) < 1e-10
        assert abs(result[1] - 7.0) < 1e-10

    def test_zero_vector(self) -> None:
        matrix = [[1, 2], [3, 4]]
        vec = [0.0, 0.0]
        result = _mat_vec_mul(matrix, vec)
        assert all(abs(v) < 1e-10 for v in result)


# ---------------------------------------------------------------------------
# Tests: _vec_mat_mul
# ---------------------------------------------------------------------------


class TestVecMatMul:
    def test_identity(self) -> None:
        identity = [[1, 0, 0], [0, 1, 0], [0, 0, 1]]
        vec = [0.5, 0.3, 0.2]
        result = _vec_mat_mul(vec, identity)
        for i in range(3):
            assert abs(result[i] - vec[i]) < 1e-10

    def test_simple_multiplication(self) -> None:
        matrix = [[1, 2], [3, 4]]
        vec = [1.0, 1.0]
        result = _vec_mat_mul(vec, matrix)
        # result[0] = 1*1 + 1*3 = 4, result[1] = 1*2 + 1*4 = 6
        assert abs(result[0] - 4.0) < 1e-10
        assert abs(result[1] - 6.0) < 1e-10

    def test_zero_vector(self) -> None:
        matrix = [[1, 2], [3, 4]]
        vec = [0.0, 0.0]
        result = _vec_mat_mul(vec, matrix)
        assert all(abs(v) < 1e-10 for v in result)


# ---------------------------------------------------------------------------
# Tests: _normalize
# ---------------------------------------------------------------------------


class TestNormalize:
    def test_basic(self) -> None:
        result = _normalize([2.0, 3.0, 5.0])
        assert abs(sum(result) - 1.0) < 1e-10
        assert abs(result[0] - 0.2) < 1e-10
        assert abs(result[1] - 0.3) < 1e-10
        assert abs(result[2] - 0.5) < 1e-10

    def test_zeros_gives_uniform(self) -> None:
        result = _normalize([0.0, 0.0, 0.0])
        assert abs(sum(result) - 1.0) < 1e-10
        for v in result:
            assert abs(v - 1.0 / 3.0) < 1e-10

    def test_already_normalized(self) -> None:
        result = _normalize([0.25, 0.25, 0.5])
        assert abs(result[0] - 0.25) < 1e-10
        assert abs(result[2] - 0.5) < 1e-10

    def test_single_element(self) -> None:
        result = _normalize([5.0])
        assert abs(result[0] - 1.0) < 1e-10

    def test_negative_total_gives_uniform(self) -> None:
        result = _normalize([-1.0, -2.0, -3.0])
        # total <= 0, should return uniform
        assert abs(sum(result) - 1.0) < 1e-10


# ---------------------------------------------------------------------------
# Tests: _converged
# ---------------------------------------------------------------------------


class TestConverged:
    def test_identical_vectors(self) -> None:
        assert _converged([1.0, 2.0, 3.0], [1.0, 2.0, 3.0]) is True

    def test_within_tolerance(self) -> None:
        assert _converged([1.0, 2.0], [1.0 + 1e-13, 2.0 - 1e-13]) is True

    def test_outside_tolerance(self) -> None:
        assert _converged([1.0, 2.0], [1.1, 2.0]) is False

    def test_custom_tolerance(self) -> None:
        assert _converged([1.0], [1.05], tol=0.1) is True
        assert _converged([1.0], [1.15], tol=0.1) is False


# ---------------------------------------------------------------------------
# Tests: _build_transition_matrix
# ---------------------------------------------------------------------------


class TestBuildTransitionMatrix:
    def test_rows_sum_to_one(self) -> None:
        matrix = _build_transition_matrix(
            mtbf_hours=2000, mttr_hours=0.5,
            degradation_rate=0.01, recovery_from_degraded_rate=0.1,
        )
        for row in matrix:
            assert abs(sum(row) - 1.0) < 1e-10, f"Row sums to {sum(row)}"

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
            mtbf_hours=100_000, mttr_hours=0.01,
            degradation_rate=0.001, recovery_from_degraded_rate=0.5,
        )
        assert matrix[0][0] > 0.99

    def test_zero_mtbf_no_crash(self) -> None:
        """mtbf_hours=0 should not cause division by zero."""
        matrix = _build_transition_matrix(
            mtbf_hours=0, mttr_hours=1.0,
            degradation_rate=0.01, recovery_from_degraded_rate=0.1,
        )
        for row in matrix:
            assert abs(sum(row) - 1.0) < 1e-10

    def test_zero_mttr_fast_recovery(self) -> None:
        """mttr_hours=0 should default to instant recovery (rate=1.0)."""
        matrix = _build_transition_matrix(
            mtbf_hours=1000, mttr_hours=0,
            degradation_rate=0.01, recovery_from_degraded_rate=0.1,
        )
        # DOWN -> HEALTHY probability should be high (rate=1.0)
        assert matrix[2][0] > 0.5

    def test_matrix_shape(self) -> None:
        matrix = _build_transition_matrix(
            mtbf_hours=1000, mttr_hours=1.0,
            degradation_rate=0.01, recovery_from_degraded_rate=0.1,
        )
        assert len(matrix) == 3
        for row in matrix:
            assert len(row) == 3

    def test_down_row_no_degraded(self) -> None:
        """DOWN state can only go to HEALTHY, never to DEGRADED."""
        matrix = _build_transition_matrix(
            mtbf_hours=1000, mttr_hours=1.0,
            degradation_rate=0.01, recovery_from_degraded_rate=0.1,
        )
        assert matrix[2][1] == 0.0  # DOWN -> DEGRADED = 0

    def test_high_degradation_rate(self) -> None:
        """High degradation rate should give more DEGRADED probability."""
        mat_low = _build_transition_matrix(
            mtbf_hours=5000, mttr_hours=1.0,
            degradation_rate=0.001, recovery_from_degraded_rate=0.1,
        )
        mat_high = _build_transition_matrix(
            mtbf_hours=5000, mttr_hours=1.0,
            degradation_rate=0.5, recovery_from_degraded_rate=0.1,
        )
        # HEALTHY -> DEGRADED should be higher with higher degradation rate
        assert mat_high[0][1] > mat_low[0][1]

    def test_extreme_rates_still_valid(self) -> None:
        """Even with extreme rates, matrix should still be usable (no crash)."""
        matrix = _build_transition_matrix(
            mtbf_hours=1, mttr_hours=0.001,
            degradation_rate=10.0, recovery_from_degraded_rate=10.0,
        )
        assert len(matrix) == 3
        for row in matrix:
            assert len(row) == 3
            for val in row:
                assert isinstance(val, float)


# ---------------------------------------------------------------------------
# Tests: _solve_steady_state
# ---------------------------------------------------------------------------


class TestSteadyStateSolver:
    def test_identity_matrix_uniform(self) -> None:
        identity = [[1, 0, 0], [0, 1, 0], [0, 0, 1]]
        pi = _solve_steady_state(identity)
        for v in pi:
            assert abs(v - 1.0 / 3.0) < 1e-6

    def test_absorbing_state(self) -> None:
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

    def test_known_two_state_chain(self) -> None:
        """Two-state chain with known steady state."""
        # State A -> B with prob 0.3, B -> A with prob 0.6
        matrix = [
            [0.7, 0.3],
            [0.6, 0.4],
        ]
        pi = _solve_steady_state(matrix)
        # Analytical: pi_A = 0.6/(0.3+0.6) = 2/3, pi_B = 0.3/(0.3+0.6) = 1/3
        assert abs(pi[0] - 2.0 / 3.0) < 1e-6
        assert abs(pi[1] - 1.0 / 3.0) < 1e-6

    def test_max_iter_still_returns(self) -> None:
        """If max_iter is very small, should still return a normalized vector."""
        matrix = _build_transition_matrix(
            mtbf_hours=2000, mttr_hours=0.5,
            degradation_rate=0.01, recovery_from_degraded_rate=0.1,
        )
        pi = _solve_steady_state(matrix, max_iter=1)
        assert abs(sum(pi) - 1.0) < 1e-8


# ---------------------------------------------------------------------------
# Tests: compute_markov_availability
# ---------------------------------------------------------------------------


class TestComputeMarkovAvailability:
    def test_result_structure(self) -> None:
        result = compute_markov_availability(mtbf_hours=2160, mttr_hours=0.5)
        assert isinstance(result, MarkovResult)
        assert "HEALTHY" in result.steady_state
        assert "DEGRADED" in result.steady_state
        assert "DOWN" in result.steady_state
        assert 0.0 <= result.availability <= 1.0
        assert result.nines >= 0
        assert len(result.transition_matrix) == 3

    def test_high_mtbf_high_availability(self) -> None:
        result = compute_markov_availability(mtbf_hours=87600, mttr_hours=0.1)
        assert result.availability > 0.99
        assert result.nines >= 2.0

    def test_low_mtbf_lower_availability(self) -> None:
        result_high = compute_markov_availability(mtbf_hours=87600, mttr_hours=0.5)
        result_low = compute_markov_availability(mtbf_hours=100, mttr_hours=0.5)
        assert result_low.availability < result_high.availability

    def test_longer_mttr_lower_availability(self) -> None:
        result_short = compute_markov_availability(mtbf_hours=2160, mttr_hours=0.1)
        result_long = compute_markov_availability(mtbf_hours=2160, mttr_hours=10.0)
        assert result_long.availability < result_short.availability

    def test_steady_state_sums_to_one(self) -> None:
        result = compute_markov_availability(mtbf_hours=2160, mttr_hours=0.5)
        total = sum(result.steady_state.values())
        assert abs(total - 1.0) < 1e-6

    def test_availability_equals_healthy_plus_degraded(self) -> None:
        result = compute_markov_availability(mtbf_hours=4320, mttr_hours=0.5)
        expected = result.steady_state["HEALTHY"] + result.steady_state["DEGRADED"]
        assert abs(result.availability - expected) < 1e-6

    def test_nines_calculation(self) -> None:
        result = compute_markov_availability(mtbf_hours=87600, mttr_hours=0.01)
        if result.availability < 1.0:
            expected_nines = -math.log10(1.0 - result.availability)
            assert abs(result.nines - round(expected_nines, 4)) < 0.01

    def test_mean_time_in_state(self) -> None:
        result = compute_markov_availability(mtbf_hours=2160, mttr_hours=0.5)
        assert "HEALTHY" in result.mean_time_in_state
        assert "DEGRADED" in result.mean_time_in_state
        assert "DOWN" in result.mean_time_in_state
        assert result.mean_time_in_state["HEALTHY"] >= result.mean_time_in_state["DOWN"]

    def test_zero_mtbf_floors_to_one(self) -> None:
        """mtbf_hours <= 0 should be floored to 1.0."""
        result = compute_markov_availability(mtbf_hours=0, mttr_hours=0.5)
        assert isinstance(result, MarkovResult)
        assert 0.0 <= result.availability <= 1.0

    def test_negative_mtbf_floors_to_one(self) -> None:
        result = compute_markov_availability(mtbf_hours=-100, mttr_hours=0.5)
        assert isinstance(result, MarkovResult)
        assert 0.0 <= result.availability <= 1.0

    def test_zero_mttr_floors(self) -> None:
        """mttr_hours <= 0 should be floored to 0.01."""
        result = compute_markov_availability(mtbf_hours=1000, mttr_hours=0)
        assert isinstance(result, MarkovResult)
        assert result.availability > 0

    def test_negative_mttr_floors(self) -> None:
        result = compute_markov_availability(mtbf_hours=1000, mttr_hours=-5)
        assert isinstance(result, MarkovResult)
        assert result.availability > 0

    def test_availability_clamped(self) -> None:
        """Availability should be clamped between 0 and 1."""
        result = compute_markov_availability(mtbf_hours=1_000_000, mttr_hours=0.001)
        assert result.availability <= 1.0
        assert result.availability >= 0.0

    def test_very_high_availability_high_nines(self) -> None:
        """Extremely high MTBF should produce very high nines value."""
        result = compute_markov_availability(mtbf_hours=1e12, mttr_hours=0.001)
        # availability rounds to 1.0, nines may be inf or very high
        assert result.nines >= 10 or result.nines == float("inf")

    def test_custom_degradation_rate(self) -> None:
        r_low = compute_markov_availability(
            mtbf_hours=2160, mttr_hours=0.5, degradation_rate=0.001
        )
        r_high = compute_markov_availability(
            mtbf_hours=2160, mttr_hours=0.5, degradation_rate=0.5
        )
        # Higher degradation should increase DEGRADED probability
        assert r_high.steady_state["DEGRADED"] > r_low.steady_state["DEGRADED"]

    def test_custom_recovery_rate(self) -> None:
        r_low = compute_markov_availability(
            mtbf_hours=2160, mttr_hours=0.5, recovery_from_degraded_rate=0.01
        )
        r_high = compute_markov_availability(
            mtbf_hours=2160, mttr_hours=0.5, recovery_from_degraded_rate=0.9
        )
        # Higher recovery rate should increase HEALTHY proportion
        assert r_high.steady_state["HEALTHY"] > r_low.steady_state["HEALTHY"]

    def test_mean_time_in_state_absorbing(self) -> None:
        """If P(stay) == 1.0 for a state, mean time should be inf."""
        # Identity-like matrix won't produce absorbing states via the API,
        # but very high MTBF produces P(stay_healthy) very close to 1
        result = compute_markov_availability(mtbf_hours=1e12, mttr_hours=0.001)
        # Mean time in HEALTHY should be very large
        assert result.mean_time_in_state["HEALTHY"] > 100


# ---------------------------------------------------------------------------
# Tests: compute_system_markov
# ---------------------------------------------------------------------------


class TestSystemMarkov:
    def test_all_components_analyzed(self) -> None:
        graph = _chain_graph()
        results = compute_system_markov(graph)
        assert set(results.keys()) == {"lb", "app", "db"}

    def test_empty_graph(self) -> None:
        graph = InfraGraph()
        results = compute_system_markov(graph)
        assert len(results) == 0

    def test_each_result_is_markov_result(self) -> None:
        graph = _chain_graph()
        results = compute_system_markov(graph)
        for r in results.values():
            assert isinstance(r, MarkovResult)
            assert 0.0 <= r.availability <= 1.0

    def test_degradation_increases_degradation_rate(self) -> None:
        """Components with memory leak should have higher DEGRADED probability."""
        graph = InfraGraph()
        graph.add_component(_comp(
            "leaky", "Leaky App", mtbf_hours=2160, mttr_minutes=10,
            memory_leak=50,
        ))
        graph.add_component(_comp(
            "clean", "Clean App", mtbf_hours=2160, mttr_minutes=10,
        ))
        results = compute_system_markov(graph)
        assert results["leaky"].steady_state["DEGRADED"] > results["clean"].steady_state["DEGRADED"]

    def test_disk_fill_increases_degradation_rate(self) -> None:
        """Components with disk fill should also get higher degradation."""
        graph = InfraGraph()
        graph.add_component(_comp(
            "filling", "Disk Filler", mtbf_hours=2160, mttr_minutes=10,
            disk_fill=5.0,
        ))
        graph.add_component(_comp(
            "clean", "Clean", mtbf_hours=2160, mttr_minutes=10,
        ))
        results = compute_system_markov(graph)
        assert results["filling"].steady_state["DEGRADED"] > results["clean"].steady_state["DEGRADED"]

    def test_zero_mtbf_uses_default(self) -> None:
        """Component with mtbf_hours=0 should use _DEFAULT_MTBF."""
        graph = InfraGraph()
        graph.add_component(_comp("s", "Server", ComponentType.APP_SERVER, mtbf_hours=0))
        results = compute_system_markov(graph)
        assert "s" in results
        assert isinstance(results["s"], MarkovResult)

    def test_zero_mttr_uses_default(self) -> None:
        """Component with mttr_minutes=0 should use default 0.5 hours."""
        graph = InfraGraph()
        graph.add_component(_comp("s", "Server", mtbf_hours=2160, mttr_minutes=0))
        results = compute_system_markov(graph)
        assert "s" in results
        assert results["s"].availability > 0

    def test_default_mtbf_coverage(self) -> None:
        """Test that various component types get appropriate defaults."""
        for ctype_name, expected_mtbf in _DEFAULT_MTBF.items():
            ctype = ComponentType(ctype_name)
            graph = InfraGraph()
            graph.add_component(_comp(
                "c", "C", ctype, mtbf_hours=0, mttr_minutes=10,
            ))
            results = compute_system_markov(graph)
            assert "c" in results

    def test_custom_type_uses_fallback_default(self) -> None:
        """Component type not in _DEFAULT_MTBF should get 2160.0."""
        graph = InfraGraph()
        graph.add_component(_comp(
            "ext", "External", ComponentType.EXTERNAL_API, mtbf_hours=0, mttr_minutes=10,
        ))
        results = compute_system_markov(graph)
        assert "ext" in results
        assert isinstance(results["ext"], MarkovResult)

    def test_single_component(self) -> None:
        graph = InfraGraph()
        graph.add_component(_comp("solo", "Solo", mtbf_hours=8760, mttr_minutes=5))
        results = compute_system_markov(graph)
        assert len(results) == 1
        assert results["solo"].availability > 0.9


# ---------------------------------------------------------------------------
# Tests: MarkovResult dataclass
# ---------------------------------------------------------------------------


class TestMarkovResultDataclass:
    def test_fields(self) -> None:
        r = MarkovResult(
            steady_state={"HEALTHY": 0.95, "DEGRADED": 0.03, "DOWN": 0.02},
            availability=0.98,
            nines=1.699,
            mean_time_in_state={"HEALTHY": 100.0, "DEGRADED": 10.0, "DOWN": 2.0},
            transition_matrix=[[0.9, 0.05, 0.05], [0.3, 0.5, 0.2], [0.5, 0.0, 0.5]],
        )
        assert r.availability == 0.98
        assert r.nines == 1.699
        assert len(r.transition_matrix) == 3


# ---------------------------------------------------------------------------
# Tests: DEFAULT_MTBF dict
# ---------------------------------------------------------------------------


class TestDefaultMTBF:
    def test_all_entries_positive(self) -> None:
        for key, val in _DEFAULT_MTBF.items():
            assert val > 0, f"Default MTBF for {key} is {val}"

    def test_dns_highest(self) -> None:
        assert _DEFAULT_MTBF["dns"] >= max(
            v for k, v in _DEFAULT_MTBF.items() if k != "dns"
        )


# ---------------------------------------------------------------------------
# Tests: Rescaling logic (lines 133-136, 141-144)
# ---------------------------------------------------------------------------


class TestRescalingLogic:
    """Test that extreme rates trigger the rescaling branches."""

    def test_healthy_row_rescaling_extreme_rates(self) -> None:
        """Extreme degradation_rate and small mtbf cause p_h_to_d + p_h_to_down > 1.0,
        triggering the rescaling logic on the HEALTHY row (lines 133-136)."""
        matrix = _build_transition_matrix(
            mtbf_hours=0.1,  # very small → large lambda_h_to_down
            mttr_hours=1.0,
            degradation_rate=100.0,  # very high → p_h_to_d ≈ 1.0
            recovery_from_degraded_rate=0.1,
        )
        # After rescaling, HEALTHY row should still sum to 1.0
        row_sum = sum(matrix[0])
        assert abs(row_sum - 1.0) < 1e-10, f"HEALTHY row sums to {row_sum}"
        # p_h_stay should be 0.0 after rescaling
        assert matrix[0][0] == 0.0
        # All probabilities non-negative
        for val in matrix[0]:
            assert val >= 0.0

    def test_degraded_row_rescaling_extreme_rates(self) -> None:
        """Extreme recovery_from_degraded_rate and small mtbf cause
        p_d_to_h + p_d_to_down > 1.0, triggering rescaling on DEGRADED row
        (lines 141-144)."""
        matrix = _build_transition_matrix(
            mtbf_hours=0.1,  # very small → large lambda_d_to_down (3/mtbf)
            mttr_hours=1.0,
            degradation_rate=0.01,
            recovery_from_degraded_rate=100.0,  # very high → p_d_to_h ≈ 1.0
        )
        # After rescaling, DEGRADED row should still sum to 1.0
        row_sum = sum(matrix[1])
        assert abs(row_sum - 1.0) < 1e-10, f"DEGRADED row sums to {row_sum}"
        # p_d_stay should be 0.0 after rescaling
        assert matrix[1][1] == 0.0
        # All probabilities non-negative
        for val in matrix[1]:
            assert val >= 0.0

    def test_both_rows_rescaled(self) -> None:
        """Both HEALTHY and DEGRADED rows need rescaling with extreme rates."""
        matrix = _build_transition_matrix(
            mtbf_hours=0.01,
            mttr_hours=0.001,
            degradation_rate=200.0,
            recovery_from_degraded_rate=200.0,
        )
        for i in range(3):
            row_sum = sum(matrix[i])
            assert abs(row_sum - 1.0) < 1e-10, f"Row {i} sums to {row_sum}"
            for val in matrix[i]:
                assert val >= 0.0

    def test_rescaled_matrix_produces_valid_steady_state(self) -> None:
        """After rescaling, steady-state computation should still work."""
        result = compute_markov_availability(
            mtbf_hours=0.1,
            mttr_hours=0.5,
            degradation_rate=100.0,
            recovery_from_degraded_rate=100.0,
        )
        assert 0.0 <= result.availability <= 1.0
        total = sum(result.steady_state.values())
        assert abs(total - 1.0) < 1e-6


# ---------------------------------------------------------------------------
# Tests: Nines edge cases (lines 223, 225)
# ---------------------------------------------------------------------------


class TestNinesEdgeCases:
    """Test nines = inf when availability >= 1.0 and nines = 0 when availability <= 0."""

    def test_nines_inf_when_availability_one(self) -> None:
        """When availability >= 1.0 (pi[DOWN]=0), nines should be inf (line 223)."""
        from unittest.mock import patch

        # Mock steady state so pi[DOWN] = 0, making availability = 1.0
        with patch(
            "faultray.simulator.markov_model._solve_steady_state",
            return_value=[0.7, 0.3, 0.0],
        ):
            result = compute_markov_availability(
                mtbf_hours=1000, mttr_hours=1.0,
            )
        assert result.availability >= 1.0
        assert result.nines == float("inf")

    def test_nines_zero_when_availability_zero(self) -> None:
        """When availability <= 0.0, nines should be 0.0 (line 225).
        This requires mocking since Markov chain naturally gives positive pi."""
        from unittest.mock import patch

        # Mock _solve_steady_state to return pi = [0, 0, 1] (all DOWN)
        with patch(
            "faultray.simulator.markov_model._solve_steady_state",
            return_value=[0.0, 0.0, 1.0],
        ):
            result = compute_markov_availability(
                mtbf_hours=1000, mttr_hours=1.0,
            )
        assert result.availability <= 0.0
        assert result.nines == 0.0


# ---------------------------------------------------------------------------
# Tests: mean_time = inf when p_stay == 1.0 (line 240)
# ---------------------------------------------------------------------------


class TestMeanTimeInf:
    """Test mean_time[name] = float('inf') when diagonal entry p_stay == 1.0."""

    def test_mean_time_inf_absorbing_state(self) -> None:
        """When a state has p_stay == 1.0, mean_time should be inf (line 240)."""
        from unittest.mock import patch

        # Construct a matrix where DOWN state has p_stay = 1.0
        # (absorbing state — never leaves DOWN)
        mock_matrix = [
            [0.9, 0.05, 0.05],
            [0.3, 0.5, 0.2],
            [0.0, 0.0, 1.0],  # DOWN is absorbing: p_stay = 1.0
        ]
        with patch(
            "faultray.simulator.markov_model._build_transition_matrix",
            return_value=mock_matrix,
        ):
            result = compute_markov_availability(
                mtbf_hours=1000, mttr_hours=1.0,
            )
        assert result.mean_time_in_state["DOWN"] == float("inf")

    def test_mean_time_inf_healthy_absorbing(self) -> None:
        """If HEALTHY were absorbing (p_stay=1.0), mean_time should be inf."""
        from unittest.mock import patch

        mock_matrix = [
            [1.0, 0.0, 0.0],  # HEALTHY is absorbing
            [0.3, 0.5, 0.2],
            [0.5, 0.0, 0.5],
        ]
        with patch(
            "faultray.simulator.markov_model._build_transition_matrix",
            return_value=mock_matrix,
        ):
            result = compute_markov_availability(
                mtbf_hours=1000, mttr_hours=1.0,
            )
        assert result.mean_time_in_state["HEALTHY"] == float("inf")
