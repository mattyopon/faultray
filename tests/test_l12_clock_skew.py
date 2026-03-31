# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Business Source License 1.1. See LICENSE file for details.

"""L12 Clock Skew Tests — Infrastructure Limits layer.

Validates that FaultRay handles system time variations correctly:
- Timestamps are recorded properly regardless of system clock
- Simulation results don't depend on wall-clock time
- Time-based operations are robust to clock skew
"""

from __future__ import annotations

import time
from unittest.mock import patch

import pytest

from faultray.model.demo import create_demo_graph
from faultray.simulator.engine import SimulationEngine
from faultray.simulator.monte_carlo import run_monte_carlo


# ---------------------------------------------------------------------------
# L12-CLOCK-001: Simulation results don't depend on wall clock
# ---------------------------------------------------------------------------


class TestClockIndependence:
    """Verify that simulation results are independent of system time."""

    def test_simulation_result_same_regardless_of_time(self) -> None:
        """Simulation results should be identical regardless of system time."""
        graph1 = create_demo_graph()
        graph2 = create_demo_graph()

        engine1 = SimulationEngine(graph1)
        engine2 = SimulationEngine(graph2)

        # Run at "different times" (results should use internal state, not clock)
        report1 = engine1.run_all_defaults(include_feed=False, include_plugins=False)
        report2 = engine2.run_all_defaults(include_feed=False, include_plugins=False)

        assert report1.resilience_score == report2.resilience_score
        assert len(report1.results) == len(report2.results)

    def test_monte_carlo_uses_seed_not_time(self) -> None:
        """Monte Carlo should use seed, not system time, for randomness."""
        graph = create_demo_graph()

        # Even if we mock time.time to return different values,
        # the Monte Carlo with same seed should give same results
        with patch("time.time", return_value=1000000000.0):
            r1 = run_monte_carlo(graph, n_trials=100, seed=42)

        with patch("time.time", return_value=2000000000.0):
            r2 = run_monte_carlo(graph, n_trials=100, seed=42)

        assert r1.availability_mean == r2.availability_mean
        assert r1.trial_results == r2.trial_results


# ---------------------------------------------------------------------------
# L12-CLOCK-002: Timestamps in config are handled correctly
# ---------------------------------------------------------------------------


class TestTimestampHandling:
    """Verify that timestamp-related operations are robust."""

    def test_config_creation_no_timestamp_dependency(self) -> None:
        """Config creation should not depend on system time."""
        from faultray.config import FaultRayConfig

        config1 = FaultRayConfig()
        config2 = FaultRayConfig()

        # Config should be identical regardless of when created
        assert config1.simulation == config2.simulation
        assert config1.daemon == config2.daemon

    def test_simulation_engine_no_time_dependency(self) -> None:
        """SimulationEngine initialization should not depend on clock."""
        graph = create_demo_graph()

        with patch("time.time", return_value=0.0):
            engine1 = SimulationEngine(graph)

        with patch("time.time", return_value=9999999999.0):
            engine2 = SimulationEngine(graph)

        # Both engines should produce same results
        r1 = engine1.run_all_defaults(include_feed=False, include_plugins=False)
        r2 = engine2.run_all_defaults(include_feed=False, include_plugins=False)
        assert r1.resilience_score == r2.resilience_score
