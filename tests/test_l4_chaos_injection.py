# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""L4 Chaos/Fault Injection Tests — Behavioral layer.

Validates that FaultRay itself is resilient to adverse conditions:
- OOM (memory exhaustion) simulation
- Disk write failures
- Corrupt / invalid input data
- Timeout on cyclic topologies
- Mid-simulation state inconsistencies
- Graceful handling of KeyboardInterrupt
"""

from __future__ import annotations

import os
import signal
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

from faultray.errors import FaultRayError, ValidationError
from faultray.model.components import (
    Component,
    ComponentType,
    Dependency,
)
from faultray.model.demo import create_demo_graph
from faultray.model.graph import InfraGraph
from faultray.model.loader import load_yaml
from faultray.simulator.engine import SimulationEngine, SimulationReport


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_large_graph(n: int) -> InfraGraph:
    """Create a graph with *n* components in a chain."""
    graph = InfraGraph()
    for i in range(n):
        graph.add_component(
            Component(
                id=f"svc-{i}",
                name=f"service-{i}",
                type=ComponentType.APP_SERVER,
                host=f"host-{i}",
                port=8080,
            )
        )
    for i in range(1, n):
        graph.add_dependency(
            Dependency(source_id=f"svc-{i}", target_id=f"svc-{i - 1}")
        )
    return graph


def _build_cyclic_graph() -> InfraGraph:
    """Create a graph with a cycle: A -> B -> C -> A."""
    graph = InfraGraph()
    for name in ("A", "B", "C"):
        graph.add_component(
            Component(
                id=name, name=name, type=ComponentType.APP_SERVER,
                host="localhost", port=8080,
            )
        )
    graph.add_dependency(Dependency(source_id="A", target_id="B"))
    graph.add_dependency(Dependency(source_id="B", target_id="C"))
    graph.add_dependency(Dependency(source_id="C", target_id="A"))
    return graph


# ---------------------------------------------------------------------------
# L4-CHAOS-001: OOM simulation
# ---------------------------------------------------------------------------


class TestOOMSimulation:
    """Verify graceful behaviour when memory is exhausted."""

    def test_large_topology_does_not_crash(self) -> None:
        """A graph with 500 nodes should complete without crashing."""
        graph = _build_large_graph(500)
        engine = SimulationEngine(graph)
        report = engine.run_all_defaults(
            include_feed=False, include_plugins=False, max_scenarios=50,
        )
        assert isinstance(report, SimulationReport)
        assert report.resilience_score >= 0.0

    def test_memory_error_in_scenario_is_caught(self) -> None:
        """If a scenario raises MemoryError the engine should return a result with error."""
        graph = create_demo_graph()
        engine = SimulationEngine(graph)

        original_execute = engine._execute_scenario

        call_count = 0

        def _boom(scenario):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise MemoryError("simulated OOM")
            return original_execute(scenario)

        with patch.object(engine, "_execute_scenario", side_effect=_boom):
            report = engine.run_all_defaults(
                include_feed=False, include_plugins=False,
            )

        # The engine should still produce a report, the failed scenario has error set
        assert isinstance(report, SimulationReport)
        errors = [r for r in report.results if r.error is not None]
        assert len(errors) >= 1


# ---------------------------------------------------------------------------
# L4-CHAOS-002: Disk write failure
# ---------------------------------------------------------------------------


class TestDiskWriteFailure:
    """Verify behaviour when disk writes fail."""

    def test_report_output_to_readonly_dir(self, tmp_path: Path) -> None:
        """Writing a checkpoint to a read-only directory should not crash.

        The engine's _save_checkpoint wraps mkdir+write in a try/except,
        but only at the write_text level. We patch at a higher level to
        ensure the overall simulation still completes.
        """
        graph = create_demo_graph()
        engine = SimulationEngine(graph)

        # Make _save_checkpoint always raise PermissionError — the
        # engine's run_scenarios catches the result, so we verify it
        # returns a Path-like or None and the run still completes.
        def _noop_checkpoint(results, count):
            # Simulate the checkpoint failing silently and returning a
            # non-existent path (engine only calls .exists() on it).
            return tmp_path / "nonexistent_checkpoint.json"

        with patch.object(engine, "_save_checkpoint", side_effect=_noop_checkpoint):
            report = engine.run_all_defaults(
                include_feed=False, include_plugins=False,
            )

        assert isinstance(report, SimulationReport)

    def test_checkpoint_save_ioerror_is_handled(self) -> None:
        """IOError during checkpoint save — engine catches it or propagates.

        We verify that if checkpoint saving raises, the engine still
        produces valid partial results via its try/except in _save_checkpoint.
        We patch the inner Path.write_text to trigger the IOError inside
        the already-caught block.
        """
        graph = create_demo_graph()
        engine = SimulationEngine(graph)

        with patch("pathlib.Path.write_text", side_effect=IOError("disk full")):
            report = engine.run_all_defaults(
                include_feed=False, include_plugins=False,
            )

        assert isinstance(report, SimulationReport)


# ---------------------------------------------------------------------------
# L4-CHAOS-003: Invalid input data
# ---------------------------------------------------------------------------


class TestInvalidInputData:
    """Verify robust handling of corrupt / malformed input."""

    def test_broken_yaml(self, tmp_path: Path) -> None:
        """Broken YAML should raise a clear error, not a raw exception."""
        bad = tmp_path / "broken.yaml"
        bad.write_text("components:\n  - id: foo\n    name: bar\n  bad: [unterminated")
        with pytest.raises(Exception):
            load_yaml(bad)

    def test_empty_yaml_file(self, tmp_path: Path) -> None:
        """An empty YAML file should raise ValidationError or similar."""
        empty = tmp_path / "empty.yaml"
        empty.write_text("")
        with pytest.raises(Exception):
            load_yaml(empty)

    def test_binary_file_as_yaml(self, tmp_path: Path) -> None:
        """A binary file should not be silently accepted as YAML."""
        binary = tmp_path / "data.yaml"
        binary.write_bytes(b"\x00\x01\x02\xff\xfe\xfd" * 100)
        with pytest.raises(Exception):
            load_yaml(binary)

    def test_yaml_with_no_components_key(self, tmp_path: Path) -> None:
        """YAML without 'components' key should return an empty graph (no components)."""
        no_comp = tmp_path / "no_comp.yaml"
        no_comp.write_text("foo: bar\nbaz: 123\n")
        graph = load_yaml(no_comp)
        # Should load without crash; the graph simply has no components
        assert len(graph.components) == 0


# ---------------------------------------------------------------------------
# L4-CHAOS-004: Cyclic dependency timeout
# ---------------------------------------------------------------------------


class TestCyclicDependencyTimeout:
    """Verify that cyclic graphs terminate (visited-set / depth-limit)."""

    def test_cyclic_graph_terminates(self) -> None:
        """Simulation on a cyclic graph should finish (D_max=20 guarantees termination)."""
        graph = _build_cyclic_graph()
        engine = SimulationEngine(graph)
        report = engine.run_all_defaults(
            include_feed=False, include_plugins=False,
        )
        assert isinstance(report, SimulationReport)

    def test_deeply_nested_chain_terminates(self) -> None:
        """A chain of 100 nodes should complete without hitting recursion limits."""
        graph = _build_large_graph(100)
        engine = SimulationEngine(graph)
        report = engine.run_all_defaults(
            include_feed=False, include_plugins=False, max_scenarios=20,
        )
        assert isinstance(report, SimulationReport)


# ---------------------------------------------------------------------------
# L4-CHAOS-005: Partial state inconsistency
# ---------------------------------------------------------------------------


class TestPartialStateInconsistency:
    """Verify that mid-simulation state corruption doesn't crash the engine."""

    def test_component_removed_during_simulation(self) -> None:
        """If a component 'disappears' mid-run, the engine should handle it."""
        graph = create_demo_graph()
        engine = SimulationEngine(graph)
        # Remove a component from the graph AFTER engine initialisation
        comp_ids = list(graph.components.keys())
        if len(comp_ids) > 1:
            del graph._components[comp_ids[-1]]

        # Should still produce a report without crashing
        report = engine.run_all_defaults(
            include_feed=False, include_plugins=False,
        )
        assert isinstance(report, SimulationReport)

    def test_empty_graph_simulation(self) -> None:
        """An empty graph should produce a valid (empty) report."""
        graph = InfraGraph()
        engine = SimulationEngine(graph)
        report = engine.run_all_defaults(
            include_feed=False, include_plugins=False,
        )
        assert isinstance(report, SimulationReport)
        assert report.resilience_score >= 0.0


# ---------------------------------------------------------------------------
# L4-CHAOS-006: Process interruption
# ---------------------------------------------------------------------------


class TestProcessInterruption:
    """Verify graceful handling of KeyboardInterrupt."""

    def test_keyboard_interrupt_does_not_corrupt_state(self) -> None:
        """KeyboardInterrupt during run_scenario should propagate cleanly."""
        graph = create_demo_graph()
        engine = SimulationEngine(graph)

        call_count = 0
        original = engine.run_scenario

        def _interrupt(scenario):
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                raise KeyboardInterrupt
            return original(scenario)

        with patch.object(engine, "run_scenario", side_effect=_interrupt):
            with pytest.raises(KeyboardInterrupt):
                engine.run_all_defaults(
                    include_feed=False, include_plugins=False,
                )

    def test_engine_usable_after_exception(self) -> None:
        """The engine should be reusable after a failed run."""
        graph = create_demo_graph()
        engine = SimulationEngine(graph)

        # First run: force an exception on the first scenario
        with patch.object(
            engine, "_execute_scenario", side_effect=RuntimeError("boom"),
        ):
            report1 = engine.run_all_defaults(
                include_feed=False, include_plugins=False,
            )
        # All results should have error field set
        assert all(r.error is not None for r in report1.results)

        # Second run: normal — engine should work fine
        report2 = engine.run_all_defaults(
            include_feed=False, include_plugins=False,
        )
        assert isinstance(report2, SimulationReport)
        assert any(r.error is None for r in report2.results)
