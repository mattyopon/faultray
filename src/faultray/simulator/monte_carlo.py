# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""Monte Carlo availability simulation.

Runs stochastic trials sampling component MTBF from an exponential
distribution and MTTR from a log-normal distribution, then computes
per-component and system-level availability across many trials.

Uses ONLY the Python standard library (``random`` / ``math``) — no
numpy or scipy required.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

from faultray.model.graph import InfraGraph


# ---------------------------------------------------------------------------
# Helpers — stdlib replacements for numpy functions
# ---------------------------------------------------------------------------

def _percentile(data: list[float], pct: float) -> float:
    """Compute the *pct*-th percentile of *data* (0-100 scale).

    Uses linear interpolation between closest ranks (same as
    ``numpy.percentile(..., interpolation='linear')``).
    """
    if not data:
        return 0.0
    sorted_data = sorted(data)
    n = len(sorted_data)
    if n == 1:
        return sorted_data[0]
    k = (pct / 100.0) * (n - 1)
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return sorted_data[int(k)]
    d0 = sorted_data[f]
    d1 = sorted_data[c]
    return d0 + (d1 - d0) * (k - f)


def _mean(data: list[float]) -> float:
    if not data:
        return 0.0
    return sum(data) / len(data)


def _std(data: list[float]) -> float:
    """Population standard deviation."""
    if len(data) < 2:
        return 0.0
    m = _mean(data)
    variance = sum((x - m) ** 2 for x in data) / len(data)
    return math.sqrt(variance)


# ---------------------------------------------------------------------------
# Default MTBF / MTTR for sampling distributions
# ---------------------------------------------------------------------------

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

_DEFAULT_MTTR: dict[str, float] = {
    "app_server": 0.083,
    "web_server": 0.083,
    "database": 0.5,
    "cache": 0.167,
    "load_balancer": 0.033,
    "queue": 0.25,
    "dns": 0.017,
    "storage": 0.083,
}

SECONDS_PER_YEAR = 365.25 * 24 * 3600


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class MonteCarloResult:
    """Result of a Monte Carlo availability simulation."""

    n_trials: int
    availability_p50: float
    availability_p95: float
    availability_p99: float
    availability_mean: float
    availability_std: float
    annual_downtime_p50_seconds: float
    annual_downtime_p95_seconds: float
    confidence_interval_95: tuple[float, float]
    trial_results: list[float] = field(repr=False)  # individual trial availabilities


# ---------------------------------------------------------------------------
# Core simulation
# ---------------------------------------------------------------------------

def _sample_exponential(rng: random.Random, mean: float) -> float:
    """Sample from an exponential distribution with the given *mean*.

    ``random.expovariate(1/mean)`` produces samples with E[X] = mean.
    """
    if mean <= 0:
        return 0.0
    return rng.expovariate(1.0 / mean)


def _sample_lognormal(rng: random.Random, mean: float) -> float:
    """Sample from a log-normal distribution whose *underlying normal*
    has the given mean as its median.

    We set mu = ln(mean) and sigma = 0.5 (moderate variance) so that
    the median of the log-normal equals *mean*.
    """
    if mean <= 0:
        return 0.0
    sigma = 0.5
    mu = math.log(mean)
    return rng.lognormvariate(mu, sigma)


def run_monte_carlo(
    graph: InfraGraph,
    n_trials: int = 10000,
    seed: int = 42,
) -> MonteCarloResult:
    """Run a Monte Carlo simulation of system availability.

    Algorithm (per trial):
      1. For each component, sample MTBF from Exponential(mean=component_mtbf).
      2. For each component, sample MTTR from LogNormal(median=component_mttr).
      3. Per-component availability = MTBF / (MTBF + MTTR).
      4. Apply redundancy: tier_avail = 1 - (1 - A)^replicas.
      5. System availability = product of critical-path tier availabilities.

    Critical-path determination matches the 3-Layer model: a component is
    on the critical path if it has ``requires``-type dependents or if it has
    no dependents at all (leaf/standalone).

    Parameters
    ----------
    graph:
        Infrastructure graph to simulate.
    n_trials:
        Number of Monte Carlo trials to run.
    seed:
        Seed for the random number generator (reproducibility).

    Returns
    -------
    MonteCarloResult
        Percentiles, mean, std, confidence interval, and per-trial results.
    """
    if not graph.components:
        return MonteCarloResult(
            n_trials=n_trials,
            availability_p50=0.0,
            availability_p95=0.0,
            availability_p99=0.0,
            availability_mean=0.0,
            availability_std=0.0,
            annual_downtime_p50_seconds=SECONDS_PER_YEAR,
            annual_downtime_p95_seconds=SECONDS_PER_YEAR,
            confidence_interval_95=(0.0, 0.0),
            trial_results=[],
        )

    rng = random.Random(seed)

    # Pre-compute per-component info
    comp_info: list[dict] = []
    for comp in graph.components.values():
        comp_type = comp.type.value
        mtbf_hours = comp.operational_profile.mtbf_hours
        if mtbf_hours <= 0:
            mtbf_hours = _DEFAULT_MTBF.get(comp_type, 2160.0)

        mttr_hours = comp.operational_profile.mttr_minutes / 60.0
        if mttr_hours <= 0:
            mttr_hours = _DEFAULT_MTTR.get(comp_type, 0.5)

        replicas = max(comp.replicas, 1)

        # Determine if this component is on the critical path
        dependents = graph.get_dependents(comp.id)
        has_requires_dependent = any(
            (edge := graph.get_dependency_edge(d.id, comp.id))
            and edge.dependency_type == "requires"
            for d in dependents
        )
        is_critical = has_requires_dependent or not dependents

        comp_info.append({
            "id": comp.id,
            "mtbf_hours": mtbf_hours,
            "mttr_hours": mttr_hours,
            "replicas": replicas,
            "is_critical": is_critical,
        })

    trial_results: list[float] = []

    for _ in range(n_trials):
        system_avail = 1.0

        for info in comp_info:
            # 1. Sample MTBF from exponential distribution
            sampled_mtbf = _sample_exponential(rng, info["mtbf_hours"])
            # Clamp to avoid degenerate zero
            sampled_mtbf = max(sampled_mtbf, 1e-6)

            # 2. Sample MTTR from log-normal distribution
            sampled_mttr = _sample_lognormal(rng, info["mttr_hours"])
            sampled_mttr = max(sampled_mttr, 1e-9)

            # 3. Single-instance availability
            a_single = sampled_mtbf / (sampled_mtbf + sampled_mttr)

            # 4. Apply redundancy: P(all replicas fail) = (1 - A)^replicas
            a_tier = 1.0 - (1.0 - a_single) ** info["replicas"]

            # 5. Multiply into system availability if on critical path
            if info["is_critical"]:
                system_avail *= a_tier

        system_avail = max(0.0, min(1.0, system_avail))
        trial_results.append(system_avail)

    # Compute statistics
    avail_mean = _mean(trial_results)
    avail_std = _std(trial_results)
    avail_p50 = _percentile(trial_results, 50)
    avail_p95 = _percentile(trial_results, 95)
    avail_p99 = _percentile(trial_results, 99)

    # 95% confidence interval for the mean (normal approximation)
    n = len(trial_results)
    se = avail_std / math.sqrt(n) if n > 0 else 0.0
    ci_lower = avail_mean - 1.96 * se
    ci_upper = avail_mean + 1.96 * se

    # Annual downtime from percentiles
    # p50 downtime: median availability -> median downtime
    dt_p50 = (1.0 - avail_p50) * SECONDS_PER_YEAR
    # p95 downtime: 5th percentile of availability -> 95th percentile of downtime
    avail_p5 = _percentile(trial_results, 5)
    dt_p95 = (1.0 - avail_p5) * SECONDS_PER_YEAR

    return MonteCarloResult(
        n_trials=n_trials,
        availability_p50=avail_p50,
        availability_p95=avail_p95,
        availability_p99=avail_p99,
        availability_mean=avail_mean,
        availability_std=avail_std,
        annual_downtime_p50_seconds=dt_p50,
        annual_downtime_p95_seconds=dt_p95,
        confidence_interval_95=(ci_lower, ci_upper),
        trial_results=trial_results,
    )
