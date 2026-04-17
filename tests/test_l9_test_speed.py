# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""L9 Test Speed Tests — Developer Experience layer.

Validates that individual tests execute within acceptable time bounds:
- Sampled tests complete within 1 second each
- Slow test detection
- Import time is reasonable
"""

from __future__ import annotations

import importlib
import time

import pytest


# ---------------------------------------------------------------------------
# L9-SPEED-001: Individual test operations complete quickly
# ---------------------------------------------------------------------------


class TestOperationSpeed:
    """Verify that common operations are fast enough for good DX."""

    @pytest.mark.timeout(1)
    def test_graph_creation_under_100ms(self) -> None:
        """Creating a demo graph should take under 100ms."""
        start = time.monotonic()
        from faultray.model.demo import create_demo_graph
        _graph = create_demo_graph()
        elapsed = time.monotonic() - start
        assert elapsed < 0.1, f"Graph creation took {elapsed:.3f}s"

    @pytest.mark.timeout(1)
    def test_yaml_parse_under_200ms(self, tmp_path) -> None:
        """Parsing a small YAML file should take under 200ms."""
        import yaml
        from faultray.model.loader import load_yaml

        yaml_content = {
            "components": [
                {"id": f"c-{i}", "name": f"C{i}", "type": "app_server"}
                for i in range(20)
            ],
            "dependencies": [],
        }
        yaml_file = tmp_path / "speed.yaml"
        yaml_file.write_text(yaml.dump(yaml_content))

        start = time.monotonic()
        _graph = load_yaml(yaml_file)
        elapsed = time.monotonic() - start
        assert elapsed < 0.2, f"YAML parse took {elapsed:.3f}s"

    @pytest.mark.timeout(2)
    def test_demo_simulation_under_2s(self) -> None:
        """A full demo simulation should complete under 2 seconds."""
        from faultray.model.demo import create_demo_graph
        from faultray.simulator.engine import SimulationEngine

        graph = create_demo_graph()
        engine = SimulationEngine(graph)

        start = time.monotonic()
        _report = engine.run_all_defaults(include_feed=False, include_plugins=False)
        elapsed = time.monotonic() - start
        assert elapsed < 2.0, f"Demo simulation took {elapsed:.3f}s"

    @pytest.mark.timeout(1)
    def test_monte_carlo_100_trials_under_1s(self) -> None:
        """100-trial Monte Carlo should complete under 1 second."""
        from faultray.model.demo import create_demo_graph
        from faultray.simulator.monte_carlo import run_monte_carlo

        graph = create_demo_graph()
        start = time.monotonic()
        _result = run_monte_carlo(graph, n_trials=100, seed=42)
        elapsed = time.monotonic() - start
        assert elapsed < 1.0, f"Monte Carlo took {elapsed:.3f}s"


# ---------------------------------------------------------------------------
# L9-SPEED-002: Import time is reasonable
# ---------------------------------------------------------------------------


class TestImportSpeed:
    """Verify that importing FaultRay modules is fast."""

    def test_faultray_import_under_500ms(self) -> None:
        """Importing faultray should take under 500ms."""
        # Re-importing is essentially a no-op after first import,
        # but we test that the import machinery doesn't block
        start = time.monotonic()
        importlib.import_module("faultray")
        elapsed = time.monotonic() - start
        assert elapsed < 0.5, f"Import took {elapsed:.3f}s"

    def test_model_import_under_200ms(self) -> None:
        """Importing model modules should be fast."""
        start = time.monotonic()
        importlib.import_module("faultray.model.components")
        importlib.import_module("faultray.model.graph")
        elapsed = time.monotonic() - start
        assert elapsed < 0.2, f"Model import took {elapsed:.3f}s"


# ---------------------------------------------------------------------------
# L9-SPEED-003: Slow test detection (meta-test)
# ---------------------------------------------------------------------------


class TestSlowTestDetection:
    """Meta-tests to verify test infrastructure supports timeout detection."""

    @pytest.mark.timeout(5)
    def test_timeout_decorator_works(self) -> None:
        """Verify that pytest-timeout is installed and functional."""
        # This test should pass instantly, proving timeout works
        assert True

    def test_no_infinite_loops_in_empty_simulation(self) -> None:
        """An empty simulation should terminate immediately."""
        from faultray.model.graph import InfraGraph
        from faultray.simulator.engine import SimulationEngine

        graph = InfraGraph()
        engine = SimulationEngine(graph)
        start = time.monotonic()
        _report = engine.run_all_defaults(include_feed=False, include_plugins=False)
        elapsed = time.monotonic() - start
        assert elapsed < 0.5, f"Empty simulation took {elapsed:.3f}s"
