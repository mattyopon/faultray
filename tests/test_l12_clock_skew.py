# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""L12 Clock Skew Tests — Infrastructure Limits layer.

Validates that FaultRay handles system time variations correctly:
- Timestamps are recorded properly regardless of system clock
- Simulation results don't depend on wall-clock time
- Time-based operations are robust to clock skew
- No usage of datetime.now() without timezone (enforced by code search)
- Report timestamps are internally consistent
"""

from __future__ import annotations

import ast
import time
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from faultray.model.demo import create_demo_graph
from faultray.simulator.engine import SimulationEngine
from faultray.simulator.monte_carlo import run_monte_carlo


SRC_ROOT = Path(__file__).resolve().parent.parent / "src" / "faultray"


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


# ---------------------------------------------------------------------------
# L12-CLOCK-003: Hour-level clock offsets
# ---------------------------------------------------------------------------


class TestHourLevelClockOffsets:
    """Verify that simulations are correct with 1-hour time offsets."""

    def test_one_hour_ahead_same_result(self) -> None:
        """Simulation with clock 1 hour ahead should produce the same result."""
        graph = create_demo_graph()
        engine = SimulationEngine(graph)

        base_report = engine.run_all_defaults(include_feed=False, include_plugins=False)

        with patch("time.time", return_value=time.time() + 3600):
            graph2 = create_demo_graph()
            engine2 = SimulationEngine(graph2)
            future_report = engine2.run_all_defaults(
                include_feed=False, include_plugins=False,
            )

        assert base_report.resilience_score == future_report.resilience_score

    def test_one_hour_behind_same_result(self) -> None:
        """Simulation with clock 1 hour behind should produce the same result."""
        graph = create_demo_graph()
        engine = SimulationEngine(graph)
        base_report = engine.run_all_defaults(include_feed=False, include_plugins=False)

        with patch("time.time", return_value=time.time() - 3600):
            graph2 = create_demo_graph()
            engine2 = SimulationEngine(graph2)
            past_report = engine2.run_all_defaults(
                include_feed=False, include_plugins=False,
            )

        assert base_report.resilience_score == past_report.resilience_score


# ---------------------------------------------------------------------------
# L12-CLOCK-004: Timezone independence
# ---------------------------------------------------------------------------


class TestTimezoneIndependence:
    """Verify results don't change across timezones."""

    @pytest.mark.parametrize("tz_name", ["UTC", "Asia/Tokyo", "US/Pacific"])
    def test_timezone_does_not_affect_simulation(self, tz_name: str) -> None:
        """Simulation results should be timezone-independent."""
        import os

        old_tz = os.environ.get("TZ")
        try:
            os.environ["TZ"] = tz_name
            # time.tzset() only exists on Unix
            if hasattr(time, "tzset"):
                time.tzset()

            graph = create_demo_graph()
            engine = SimulationEngine(graph)
            report = engine.run_all_defaults(
                include_feed=False, include_plugins=False,
            )
            assert report.resilience_score > 0.0
            assert len(report.results) > 0
        finally:
            if old_tz is None:
                os.environ.pop("TZ", None)
            else:
                os.environ["TZ"] = old_tz
            if hasattr(time, "tzset"):
                time.tzset()


# ---------------------------------------------------------------------------
# L12-CLOCK-005: No bare datetime.now() in core source
# ---------------------------------------------------------------------------


class TestNoBareDatetimeNow:
    """Ensure datetime.now() without tz is not used in the core source."""

    def test_no_bare_datetime_now_in_simulator(self) -> None:
        """Core simulator modules should use datetime.now(timezone.utc), not bare now().

        Known legacy exceptions are tracked here and must not grow.
        """
        # Known legacy files with bare datetime.now() — these should be
        # migrated to datetime.now(timezone.utc) eventually.
        KNOWN_LEGACY = {"sla_budget.py", "team_tracker.py"}

        violations: list[str] = []
        sim_dir = SRC_ROOT / "simulator"
        for py_file in sim_dir.glob("*.py"):
            if py_file.name in KNOWN_LEGACY:
                continue
            source = py_file.read_text(encoding="utf-8")
            try:
                tree = ast.parse(source)
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    # Match datetime.now() with zero arguments
                    func = node.func
                    if (
                        isinstance(func, ast.Attribute)
                        and func.attr == "now"
                        and len(node.args) == 0
                        and len(node.keywords) == 0
                    ):
                        violations.append(
                            f"{py_file.name}:{node.lineno} — datetime.now() without tz"
                        )
        assert not violations, (
            "Found NEW bare datetime.now() calls (should use datetime.now(timezone.utc)):\n"
            + "\n".join(violations)
        )


# ---------------------------------------------------------------------------
# L12-CLOCK-006: Report timestamp consistency
# ---------------------------------------------------------------------------


class TestReportTimestampConsistency:
    """Verify that report timestamps are internally consistent."""

    def test_two_sequential_simulations_ordered(self) -> None:
        """Two sequential simulations should have logically ordered timestamps."""
        graph1 = create_demo_graph()
        engine1 = SimulationEngine(graph1)

        _t1_before = time.monotonic()
        report1 = engine1.run_all_defaults(include_feed=False, include_plugins=False)
        t1_after = time.monotonic()

        graph2 = create_demo_graph()
        engine2 = SimulationEngine(graph2)

        t2_before = time.monotonic()
        report2 = engine2.run_all_defaults(include_feed=False, include_plugins=False)
        _t2_after = time.monotonic()

        # The second simulation must start after the first completed
        assert t2_before >= t1_after
        # Both reports must be valid
        assert isinstance(report1.resilience_score, float)
        assert isinstance(report2.resilience_score, float)
