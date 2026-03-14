"""Markov chain availability model for ChaosProof.

Computes steady-state availability using a 3-state continuous-time Markov
chain:  HEALTHY <-> DEGRADED -> DOWN -> HEALTHY.

Implements matrix operations manually — no numpy required.  Uses the
iterative power method to find the steady-state distribution.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from infrasim.model.graph import InfraGraph

# Default MTBF (hours) when component has no explicit profile
_DEFAULT_MTBF: dict[str, float] = {
    "app_server": 2160.0,
    "web_server": 2160.0,
    "database": 4320.0,
    "cache": 1440.0,
    "load_balancer": 8760.0,
    "queue": 2160.0,
    "dns": 43800.0,
    "storage": 8760.0,
}


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------


@dataclass
class MarkovResult:
    """Result of Markov chain steady-state analysis."""

    steady_state: dict[str, float]  # {HEALTHY: 0.95, DEGRADED: 0.03, DOWN: 0.02}
    availability: float  # P(HEALTHY) + P(DEGRADED)
    nines: float  # -log10(1 - availability)
    mean_time_in_state: dict[str, float]  # hours
    transition_matrix: list[list[float]]  # row-stochastic transition matrix


# ---------------------------------------------------------------------------
# Matrix helpers (no numpy)
# ---------------------------------------------------------------------------


def _mat_vec_mul(matrix: list[list[float]], vec: list[float]) -> list[float]:
    """Multiply a matrix by a vector: result[i] = sum(matrix[i][j] * vec[j])."""
    n = len(vec)
    result = [0.0] * n
    for i in range(n):
        for j in range(n):
            result[i] += matrix[i][j] * vec[j]
    return result


def _vec_mat_mul(vec: list[float], matrix: list[list[float]]) -> list[float]:
    """Multiply a row vector by a matrix: result[j] = sum(vec[i] * matrix[i][j])."""
    n = len(vec)
    result = [0.0] * n
    for j in range(n):
        for i in range(n):
            result[j] += vec[i] * matrix[i][j]
    return result


def _normalize(vec: list[float]) -> list[float]:
    """Normalize a vector so its elements sum to 1."""
    total = sum(vec)
    if total <= 0:
        return [1.0 / len(vec)] * len(vec)
    return [v / total for v in vec]


def _converged(v1: list[float], v2: list[float], tol: float = 1e-12) -> bool:
    """Check if two vectors are element-wise close within tolerance."""
    return all(abs(a - b) < tol for a, b in zip(v1, v2))


# ---------------------------------------------------------------------------
# Core computation
# ---------------------------------------------------------------------------


def _build_transition_matrix(
    mtbf_hours: float,
    mttr_hours: float,
    degradation_rate: float,
    recovery_from_degraded_rate: float,
) -> list[list[float]]:
    """Build a 3x3 row-stochastic transition matrix from rates.

    States: 0 = HEALTHY, 1 = DEGRADED, 2 = DOWN

    Transition rates (per hour) are converted to probabilities for a
    discrete-time approximation with a 1-hour time step:
        P(transition) = 1 - exp(-rate * dt)
    """
    dt = 1.0  # 1-hour time step

    # HEALTHY -> DEGRADED
    lambda_h_to_d = degradation_rate
    # HEALTHY -> DOWN  (direct failure rate from MTBF, reduced by degradation path)
    lambda_h_to_down = (1.0 / mtbf_hours) * 0.3 if mtbf_hours > 0 else 0.0
    # DEGRADED -> DOWN
    lambda_d_to_down = (1.0 / mtbf_hours) * 3.0 if mtbf_hours > 0 else 0.0
    # DEGRADED -> HEALTHY (recovery from degraded)
    lambda_d_to_h = recovery_from_degraded_rate
    # DOWN -> HEALTHY (repair rate from MTTR)
    lambda_down_to_h = (1.0 / mttr_hours) if mttr_hours > 0 else 1.0

    # Convert rates to transition probabilities
    def _rate_to_prob(rate: float) -> float:
        if rate <= 0:
            return 0.0
        return 1.0 - math.exp(-rate * dt)

    p_h_to_d = _rate_to_prob(lambda_h_to_d)
    p_h_to_down = _rate_to_prob(lambda_h_to_down)
    p_d_to_down = _rate_to_prob(lambda_d_to_down)
    p_d_to_h = _rate_to_prob(lambda_d_to_h)
    p_down_to_h = _rate_to_prob(lambda_down_to_h)

    # Ensure row probabilities sum to 1
    # Row 0: HEALTHY
    p_h_stay = max(0.0, 1.0 - p_h_to_d - p_h_to_down)
    if p_h_stay < 0:
        # Rescale
        total = p_h_to_d + p_h_to_down
        p_h_to_d /= total
        p_h_to_down /= total
        p_h_stay = 0.0

    # Row 1: DEGRADED
    p_d_stay = max(0.0, 1.0 - p_d_to_h - p_d_to_down)
    if p_d_stay < 0:
        total = p_d_to_h + p_d_to_down
        p_d_to_h /= total
        p_d_to_down /= total
        p_d_stay = 0.0

    # Row 2: DOWN  (can only go to HEALTHY)
    p_down_stay = max(0.0, 1.0 - p_down_to_h)

    matrix = [
        [p_h_stay, p_h_to_d, p_h_to_down],  # HEALTHY
        [p_d_to_h, p_d_stay, p_d_to_down],   # DEGRADED
        [p_down_to_h, 0.0, p_down_stay],      # DOWN
    ]

    return matrix


def _solve_steady_state(
    matrix: list[list[float]],
    max_iter: int = 100_000,
    tol: float = 1e-12,
) -> list[float]:
    """Find steady-state distribution pi using the power method.

    Iterates pi = pi * P until convergence.
    """
    n = len(matrix)
    pi = _normalize([1.0] * n)

    for _ in range(max_iter):
        pi_new = _vec_mat_mul(pi, matrix)
        pi_new = _normalize(pi_new)
        if _converged(pi, pi_new, tol):
            return pi_new
        pi = pi_new

    return _normalize(pi)


def compute_markov_availability(
    mtbf_hours: float,
    mttr_hours: float,
    degradation_rate: float = 0.01,
    recovery_from_degraded_rate: float = 0.1,
) -> MarkovResult:
    """Compute steady-state availability using a 3-state Markov model.

    Parameters
    ----------
    mtbf_hours:
        Mean time between failures in hours.
    mttr_hours:
        Mean time to repair in hours.
    degradation_rate:
        Rate of transitioning from HEALTHY to DEGRADED (transitions/hour).
    recovery_from_degraded_rate:
        Rate of recovering from DEGRADED back to HEALTHY.

    Returns
    -------
    MarkovResult
        Steady-state probabilities, availability, nines, and mean time in
        each state.
    """
    if mtbf_hours <= 0:
        mtbf_hours = 1.0
    if mttr_hours <= 0:
        mttr_hours = 0.01

    matrix = _build_transition_matrix(
        mtbf_hours, mttr_hours, degradation_rate, recovery_from_degraded_rate,
    )
    pi = _solve_steady_state(matrix)

    state_names = ["HEALTHY", "DEGRADED", "DOWN"]
    steady_state = {state_names[i]: round(pi[i], 8) for i in range(3)}

    # Availability = P(not DOWN) = P(HEALTHY) + P(DEGRADED)
    availability = pi[0] + pi[1]
    availability = max(0.0, min(1.0, availability))

    if availability >= 1.0:
        nines = float("inf")
    elif availability <= 0.0:
        nines = 0.0
    else:
        nines = -math.log10(1.0 - availability)

    # Mean time in each state (hours)
    # For state i with steady-state probability pi[i] and departure rate:
    # mean_sojourn_time = 1 / (sum of outgoing rates)
    # But for simplicity we report pi[i] * total_cycle_time.
    # Here we use the diagonal element: mean sojourn = 1 / (1 - P(i,i))
    mean_time: dict[str, float] = {}
    for i, name in enumerate(state_names):
        p_stay = matrix[i][i]
        if p_stay < 1.0:
            mean_time[name] = round(1.0 / (1.0 - p_stay), 2)
        else:
            mean_time[name] = float("inf")

    return MarkovResult(
        steady_state=steady_state,
        availability=round(availability, 8),
        nines=round(nines, 4),
        mean_time_in_state=mean_time,
        transition_matrix=matrix,
    )


def compute_system_markov(graph: InfraGraph) -> dict[str, MarkovResult]:
    """Compute Markov availability for every component in the graph.

    Returns a dict mapping component_id -> MarkovResult.
    """
    results: dict[str, MarkovResult] = {}
    for comp in graph.components.values():
        mtbf = comp.operational_profile.mtbf_hours
        if mtbf <= 0:
            mtbf = _DEFAULT_MTBF.get(comp.type.value, 2160.0)

        mttr = comp.operational_profile.mttr_minutes / 60.0
        if mttr <= 0:
            mttr = 0.5

        degradation = comp.operational_profile.degradation
        # Use degradation rates to inform the Markov model
        deg_rate = 0.01  # default
        if degradation.memory_leak_mb_per_hour > 0 or degradation.disk_fill_gb_per_hour > 0:
            deg_rate = 0.05  # higher degradation rate for leaky components

        results[comp.id] = compute_markov_availability(
            mtbf_hours=mtbf,
            mttr_hours=mttr,
            degradation_rate=deg_rate,
        )

    return results
