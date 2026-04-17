# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""L8 Reproducibility Tests — Social Trust layer.

Validates that FaultRay produces deterministic, reproducible results:
- Same input yields same output
- Seeded Monte Carlo produces identical results across runs
- Simulation results are stable across invocations
"""

from __future__ import annotations

import pytest

from faultray.model.demo import create_demo_graph
from faultray.simulator.engine import SimulationEngine
from faultray.simulator.monte_carlo import run_monte_carlo


# ---------------------------------------------------------------------------
# L8-REPRO-001: Deterministic simulation results
# ---------------------------------------------------------------------------


class TestDeterministicSimulation:
    """Verify that simulations produce identical results for same input."""

    def test_simulation_deterministic(self) -> None:
        """Two runs with the same graph should yield identical results."""
        graph1 = create_demo_graph()
        graph2 = create_demo_graph()

        engine1 = SimulationEngine(graph1)
        engine2 = SimulationEngine(graph2)

        report1 = engine1.run_all_defaults(include_feed=False, include_plugins=False)
        report2 = engine2.run_all_defaults(include_feed=False, include_plugins=False)

        assert report1.resilience_score == report2.resilience_score
        assert len(report1.results) == len(report2.results)

        for r1, r2 in zip(report1.results, report2.results):
            assert r1.risk_score == r2.risk_score
            assert r1.scenario.id == r2.scenario.id

    def test_resilience_score_stable(self) -> None:
        """Resilience score should be identical across 5 invocations."""
        scores = []
        for _ in range(5):
            graph = create_demo_graph()
            engine = SimulationEngine(graph)
            report = engine.run_all_defaults(include_feed=False, include_plugins=False)
            scores.append(report.resilience_score)

        assert len(set(scores)) == 1, f"Scores vary across runs: {scores}"


# ---------------------------------------------------------------------------
# L8-REPRO-002: Monte Carlo seed reproducibility
# ---------------------------------------------------------------------------


class TestMonteCarloReproducibility:
    """Verify seeded Monte Carlo produces identical results."""

    def test_same_seed_same_result(self) -> None:
        """Same seed should produce identical Monte Carlo results."""
        graph = create_demo_graph()

        r1 = run_monte_carlo(graph, n_trials=1000, seed=42)
        r2 = run_monte_carlo(graph, n_trials=1000, seed=42)

        assert r1.availability_mean == r2.availability_mean
        assert r1.availability_p50 == r2.availability_p50
        assert r1.availability_p95 == r2.availability_p95
        assert r1.availability_p99 == r2.availability_p99
        assert r1.availability_std == r2.availability_std
        assert r1.trial_results == r2.trial_results

    def test_different_seeds_different_results(self) -> None:
        """Different seeds should generally produce different results."""
        graph = create_demo_graph()

        r1 = run_monte_carlo(graph, n_trials=1000, seed=42)
        r2 = run_monte_carlo(graph, n_trials=1000, seed=99)

        # Individual trial results should differ (probabilistically)
        assert r1.trial_results != r2.trial_results

    def test_monte_carlo_reproducibility_across_10_runs(self) -> None:
        """Monte Carlo with fixed seed should be identical across 10 runs."""
        graph = create_demo_graph()
        means = []
        for _ in range(10):
            result = run_monte_carlo(graph, n_trials=500, seed=12345)
            means.append(result.availability_mean)

        assert len(set(means)) == 1, f"Monte Carlo means vary: {means}"


# ---------------------------------------------------------------------------
# L8-REPRO-003: Result stability
# ---------------------------------------------------------------------------


class TestResultStability:
    """Verify result values are within expected ranges."""

    def test_availability_between_0_and_1(self) -> None:
        """All availability values should be in [0, 1]."""
        graph = create_demo_graph()
        result = run_monte_carlo(graph, n_trials=100, seed=42)

        assert 0.0 <= result.availability_mean <= 1.0
        assert 0.0 <= result.availability_p50 <= 1.0
        assert 0.0 <= result.availability_p95 <= 1.0
        assert 0.0 <= result.availability_p99 <= 1.0

        for trial in result.trial_results:
            assert 0.0 <= trial <= 1.0

    def test_confidence_interval_contains_mean(self) -> None:
        """The 95% confidence interval should contain the mean."""
        graph = create_demo_graph()
        result = run_monte_carlo(graph, n_trials=1000, seed=42)

        lo, hi = result.confidence_interval_95
        assert lo <= result.availability_mean <= hi

    def test_downtime_non_negative(self) -> None:
        """Annual downtime estimates should be non-negative."""
        graph = create_demo_graph()
        result = run_monte_carlo(graph, n_trials=100, seed=42)

        assert result.annual_downtime_p50_seconds >= 0.0
        assert result.annual_downtime_p95_seconds >= 0.0
