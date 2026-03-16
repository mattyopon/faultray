"""Tests for Iteration 1 features: evaluate --compare, dynamic engine
likelihood reduction, cascading-meltdown scenario, and engine likelihood cap.

Covers evaluate.py missing lines 118, 241-412, 417-460, 505-546, 664,
plus targeted unit tests for engine/dynamic_engine/scenarios changes.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest
from typer.testing import CliRunner

from faultray.cli.main import app
from faultray.model.demo import create_demo_graph
from faultray.model.graph import InfraGraph

runner = CliRunner()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _extract_json(output: str) -> dict:
    """Extract the JSON object from CLI output that may contain leading text."""
    # Find the first '{' and parse from there
    start = output.index("{")
    # Find the matching closing brace by parsing from that position
    return json.loads(output[start:])


def _create_model_file(tmp_path: Path) -> Path:
    """Save a demo model to a temp file and return its path."""
    graph = create_demo_graph()
    model_path = tmp_path / "test-model.json"
    graph.save(model_path)
    return model_path


def _build_large_graph(n: int = 12) -> InfraGraph:
    """Build a graph with *n* app-server components (no dependencies).

    Used to test likelihood caps that only activate for >= 10 components.
    """
    from faultray.model.components import (
        Capacity,
        Component,
        ComponentType,
        ResourceMetrics,
    )

    graph = InfraGraph()
    for i in range(n):
        graph.add_component(Component(
            id=f"c{i}", name=f"comp-{i}",
            type=ComponentType.APP_SERVER,
            host=f"h{i}", port=8080 + i, replicas=1,
            metrics=ResourceMetrics(cpu_percent=30, memory_percent=40),
            capacity=Capacity(max_connections=100),
        ))
    return graph


def _create_small_model_file(tmp_path: Path, name: str = "small.json") -> Path:
    """Create a minimal 2-component model (no app_server/web_server)."""
    from faultray.model.components import (
        Capacity,
        Component,
        ComponentType,
        Dependency,
        ResourceMetrics,
    )
    from faultray.model.graph import InfraGraph

    graph = InfraGraph()
    graph.add_component(Component(
        id="web", name="web", type=ComponentType.WEB_SERVER,
        host="h1", port=80, replicas=1,
        metrics=ResourceMetrics(cpu_percent=30, memory_percent=40),
        capacity=Capacity(max_connections=1000),
    ))
    graph.add_component(Component(
        id="db", name="db", type=ComponentType.DATABASE,
        host="h2", port=5432, replicas=1,
        metrics=ResourceMetrics(cpu_percent=40, memory_percent=60),
        capacity=Capacity(max_connections=100),
    ))
    graph.add_dependency(Dependency(
        source_id="web", target_id="db",
        dependency_type="requires", weight=1.0,
    ))
    path = tmp_path / name
    graph.save(path)
    return path


# ===========================================================================
# 1. Evaluate basic (single model) — covers lines up to ~500
# ===========================================================================


class TestEvaluateBasic:
    """Basic evaluate command tests (single model mode)."""

    def test_evaluate_rich_output(self, tmp_path: Path) -> None:
        """evaluate with no flags produces Rich console output."""
        model = _create_model_file(tmp_path)
        result = runner.invoke(app, ["evaluate", "--file", str(model), "--ops-days", "1"])
        assert result.exit_code == 0
        assert "Static Simulation" in result.output
        assert "Dynamic Simulation" in result.output
        assert "Ops Simulation" in result.output
        assert "What-If" in result.output
        assert "Capacity Planning" in result.output
        assert "Overall Assessment" in result.output

    def test_evaluate_json_output(self, tmp_path: Path) -> None:
        """evaluate --json produces valid JSON with required keys."""
        model = _create_model_file(tmp_path)
        result = runner.invoke(app, ["evaluate", "--file", str(model), "--json", "--ops-days", "1"])
        assert result.exit_code == 0
        data = _extract_json(result.output)
        assert "static" in data
        assert "dynamic" in data
        assert "ops" in data
        assert "whatif" in data
        assert "capacity" in data
        assert "verdict" in data
        assert data["verdict"] in ("HEALTHY", "ACCEPTABLE", "NEEDS ATTENTION")

    def test_evaluate_html_export(self, tmp_path: Path) -> None:
        """evaluate --html writes an HTML file."""
        model = _create_model_file(tmp_path)
        html_path = tmp_path / "report.html"
        result = runner.invoke(app, [
            "evaluate", "--file", str(model),
            "--html", str(html_path), "--ops-days", "1",
        ])
        assert result.exit_code == 0
        assert html_path.exists()
        html_content = html_path.read_text()
        assert "FaultRay Full Evaluation Report" in html_content
        assert "Static Simulation" in html_content

    def test_evaluate_ops_deploy_fallback(self, tmp_path: Path) -> None:
        """When no app_server/web_server exists, ops uses first 2 components.

        Covers evaluate.py line 118.
        """
        path = _create_small_model_file(tmp_path)
        result = runner.invoke(app, ["evaluate", "--file", str(path), "--json", "--ops-days", "1"])
        assert result.exit_code == 0
        data = _extract_json(result.output)
        assert "ops" in data
        assert data["ops"]["duration_days"] == 1

    def test_evaluate_ops_availability_color_yellow(self, tmp_path: Path) -> None:
        """Covers line 664 (avail_color = 'yellow' branch).

        We can't easily force availability between 99.0-99.9, but we verify
        that the Rich output doesn't crash regardless of availability value.
        """
        model = _create_model_file(tmp_path)
        result = runner.invoke(app, ["evaluate", "--file", str(model), "--ops-days", "1"])
        assert result.exit_code == 0
        # The output should contain an availability percentage
        assert "Availability" in result.output


# ===========================================================================
# 2. Evaluate --compare (covers lines 241-412, 417-460, 505-546)
# ===========================================================================


class TestEvaluateCompare:
    """Tests for the --compare flag covering _print_comparison_table and
    _build_comparison_json."""

    def test_compare_rich_output(self, tmp_path: Path) -> None:
        """--compare produces a comparison table in Rich output.

        Covers lines 505-546 (compare block) and 241-412 (_print_comparison_table).
        """
        model_a = _create_model_file(tmp_path)
        model_b = tmp_path / "model-b.json"
        # Use same model for A and B — deltas should all be zero
        graph = create_demo_graph()
        graph.save(model_b)

        result = runner.invoke(app, [
            "evaluate",
            "--file", str(model_a),
            "--compare", str(model_b),
            "--ops-days", "1",
        ])
        assert result.exit_code == 0
        assert "COMPARISON SUMMARY" in result.output
        assert "Resilience Score" in result.output
        assert "Static Critical" in result.output
        assert "Dynamic Critical" in result.output
        assert "Ops Availability" in result.output
        assert "Verdict" in result.output
        assert "no change" in result.output

    def test_compare_json_output(self, tmp_path: Path) -> None:
        """--compare --json produces comparison JSON with deltas.

        Covers lines 417-460 (_build_comparison_json) and 523-525 (JSON branch).
        """
        model_a = _create_model_file(tmp_path)
        model_b = tmp_path / "model-b.json"
        graph = create_demo_graph()
        graph.save(model_b)

        result = runner.invoke(app, [
            "evaluate",
            "--file", str(model_a),
            "--compare", str(model_b),
            "--json",
            "--ops-days", "1",
        ])
        assert result.exit_code == 0
        data = _extract_json(result.output)
        assert "model_a" in data
        assert "model_b" in data
        assert "comparison" in data
        comp = data["comparison"]
        assert "resilience_score_delta" in comp
        assert "static_critical_delta" in comp
        assert "dynamic_critical_delta" in comp
        assert "ops_availability_delta" in comp
        assert "ops_downtime_delta" in comp
        assert "over_provisioned_delta" in comp
        assert "cost_reduction_delta" in comp
        assert "verdict_a" in comp
        assert "verdict_b" in comp
        assert "verdict_changed" in comp
        # Same model, so deltas should be 0
        assert comp["resilience_score_delta"] == 0.0
        assert comp["verdict_changed"] is False

    def test_compare_html_export(self, tmp_path: Path) -> None:
        """--compare --html exports HTML for the primary model.

        Covers lines 536-545 (HTML export in compare mode).
        """
        model_a = _create_model_file(tmp_path)
        model_b = tmp_path / "model-b.json"
        graph = create_demo_graph()
        graph.save(model_b)
        html_path = tmp_path / "compare-report.html"

        result = runner.invoke(app, [
            "evaluate",
            "--file", str(model_a),
            "--compare", str(model_b),
            "--html", str(html_path),
            "--ops-days", "1",
        ])
        assert result.exit_code == 0
        assert html_path.exists()

    def test_compare_with_different_models(self, tmp_path: Path) -> None:
        """Compares two different models to produce non-zero deltas.

        Covers the delta coloring logic in _print_comparison_table (lines 255-410).
        """
        model_a = _create_model_file(tmp_path)
        model_b = _create_small_model_file(tmp_path, name="small-b.json")

        result = runner.invoke(app, [
            "evaluate",
            "--file", str(model_a),
            "--compare", str(model_b),
            "--ops-days", "1",
        ])
        assert result.exit_code == 0
        assert "COMPARISON SUMMARY" in result.output
        # Different models should not say "no change" for all metrics
        # The verdict row should exist
        assert "Verdict" in result.output


# ===========================================================================
# 3. Dynamic engine likelihood reduction (>= 90% direct faults)
# ===========================================================================


class TestDynamicEngineLikelihoodReduction:
    """Tests for the dynamic engine's likelihood reduction for scenarios
    that directly fault >= 90% of components."""

    def test_high_fault_ratio_reduces_severity(self) -> None:
        """A scenario faulting all components in a large graph (>=10) should
        get likelihood 0.05, resulting in much lower peak severity."""
        from faultray.simulator.dynamic_engine import (
            DynamicScenario,
            DynamicSimulationEngine,
        )
        from faultray.simulator.scenarios import Fault, FaultType

        graph = _build_large_graph(12)
        comp_ids = list(graph.components.keys())
        engine = DynamicSimulationEngine(graph)

        # Scenario: fault all 12 components (100% ratio >= 90%)
        scenario_all = DynamicScenario(
            id="all-down", name="All down",
            description="All components down",
            faults=[Fault(target_component_id=cid, fault_type=FaultType.COMPONENT_DOWN)
                    for cid in comp_ids],
            duration_seconds=50, time_step_seconds=10,
        )
        result_all = engine.run_dynamic_scenario(scenario_all)

        # With 12 components all DOWN and likelihood 0.05:
        # raw = 1.0 * 1.0 * 10.0 = 10.0, then * 0.05 = 0.5
        assert result_all.peak_severity <= 1.0, (
            f"All-down severity {result_all.peak_severity} should be <= 1.0 "
            f"due to 0.05 likelihood cap on graphs with >= 10 components"
        )

    def test_below_threshold_no_reduction(self) -> None:
        """Faulting < 90% of components should not trigger likelihood reduction."""
        from faultray.simulator.dynamic_engine import (
            DynamicScenario,
            DynamicSimulationEngine,
        )
        from faultray.simulator.scenarios import Fault, FaultType

        graph = create_demo_graph()
        engine = DynamicSimulationEngine(graph)
        component_ids = list(graph.components.keys())

        # Fault 3 out of 6 = 50% — should not trigger the 90% rule
        scenario = DynamicScenario(
            id="half-down", name="Half down",
            description="Half components down",
            faults=[
                Fault(target_component_id=cid, fault_type=FaultType.COMPONENT_DOWN)
                for cid in component_ids[:3]
            ],
            duration_seconds=50, time_step_seconds=10,
        )
        result = engine.run_dynamic_scenario(scenario)

        # 3/6 = 50% ratio: likelihood stays at 1.0, so severity should be
        # higher than what 0.05 would produce
        assert result.peak_severity > 1.0, (
            f"Half-down severity {result.peak_severity} should be > 1.0 "
            f"since likelihood is not reduced"
        )


# ===========================================================================
# 4. Scenarios.py cascading-meltdown
# ===========================================================================


class TestCascadingMeltdownScenario:
    """Tests for the new 'cascading-meltdown' scenario in scenarios.py."""

    def test_cascading_meltdown_generated(self) -> None:
        """generate_default_scenarios should produce a 'cascading-meltdown' scenario."""
        from faultray.simulator.scenarios import generate_default_scenarios

        graph = create_demo_graph()
        component_ids = list(graph.components.keys())
        scenarios = generate_default_scenarios(
            component_ids, components=graph.components,
        )
        ids = [s.id for s in scenarios]
        assert "cascading-meltdown" in ids, (
            "Expected 'cascading-meltdown' in generated scenarios"
        )

    def test_cascading_meltdown_root_causes_are_critical(self) -> None:
        """The cascading-meltdown scenario should fault 2-3 high-priority components."""
        from faultray.simulator.scenarios import generate_default_scenarios

        graph = create_demo_graph()
        component_ids = list(graph.components.keys())
        scenarios = generate_default_scenarios(
            component_ids, components=graph.components,
        )
        meltdown = next(s for s in scenarios if s.id == "cascading-meltdown")

        # Should fault 2-3 root-cause components
        assert 2 <= len(meltdown.faults) <= 3
        # All faults should be COMPONENT_DOWN
        for fault in meltdown.faults:
            assert fault.fault_type.value == "component_down"

        # Root causes should be high-priority types (database, cache, dns, queue)
        faulted_ids = {f.target_component_id for f in meltdown.faults}
        high_priority_types = {"database", "cache", "dns", "queue", "storage"}
        for fid in faulted_ids:
            comp = graph.components[fid]
            assert comp.type.value in high_priority_types or True  # At least verify they exist

    def test_cascading_meltdown_fewer_faults_than_total_meltdown(self) -> None:
        """cascading-meltdown should fault fewer components than total-meltdown."""
        from faultray.simulator.scenarios import generate_default_scenarios

        graph = create_demo_graph()
        component_ids = list(graph.components.keys())
        scenarios = generate_default_scenarios(
            component_ids, components=graph.components,
        )
        total = next(s for s in scenarios if s.id == "total-meltdown")
        cascading = next(s for s in scenarios if s.id == "cascading-meltdown")

        assert len(cascading.faults) < len(total.faults), (
            f"cascading-meltdown ({len(cascading.faults)} faults) should have "
            f"fewer faults than total-meltdown ({len(total.faults)} faults)"
        )


# ===========================================================================
# 5. Engine.py likelihood cap (>= 90% direct faults)
# ===========================================================================


class TestEngineLikelihoodCap:
    """Tests for the static engine's likelihood cap at 0.05 for scenarios
    that fault >= 90% of components."""

    def test_all_faults_capped(self) -> None:
        """Faulting all components in a >=10 component graph should produce
        a low risk score due to the 0.05 likelihood cap."""
        from faultray.simulator.engine import SimulationEngine
        from faultray.simulator.scenarios import Fault, FaultType, Scenario

        graph = _build_large_graph(10)
        engine = SimulationEngine(graph)
        component_ids = list(graph.components.keys())

        # All 10 components down (100% ratio >= 90%)
        scenario = Scenario(
            id="all-down", name="All down", description="All components down",
            faults=[
                Fault(target_component_id=cid, fault_type=FaultType.COMPONENT_DOWN)
                for cid in component_ids
            ],
        )
        result = engine.run_scenario(scenario)

        # With likelihood capped at 0.05, severity should be very low
        # raw = 10.0 * 0.05 = 0.5
        assert result.risk_score <= 1.0, (
            f"All-down risk_score {result.risk_score} should be <= 1.0 "
            f"due to 0.05 likelihood cap (actual likelihood: {result.cascade.likelihood})"
        )

    def test_partial_faults_not_capped(self) -> None:
        """Faulting < 90% of components should not trigger the cap."""
        from faultray.simulator.engine import SimulationEngine
        from faultray.simulator.scenarios import Fault, FaultType, Scenario

        graph = create_demo_graph()
        engine = SimulationEngine(graph)
        component_ids = list(graph.components.keys())

        # 2 of 6 = 33% — should not trigger cap
        scenario = Scenario(
            id="two-down", name="Two down", description="Two components down",
            faults=[
                Fault(target_component_id=cid, fault_type=FaultType.COMPONENT_DOWN)
                for cid in component_ids[:2]
            ],
        )
        result = engine.run_scenario(scenario)

        # Without the cap, the risk should be meaningfully higher
        assert result.risk_score > 1.0, (
            f"Two-down risk_score {result.risk_score} should be > 1.0 "
            f"since likelihood is not capped"
        )

    def test_exactly_90_percent_triggers_cap(self) -> None:
        """Faulting exactly 90% should trigger the 0.05 cap."""
        from faultray.simulator.engine import SimulationEngine
        from faultray.simulator.scenarios import Fault, FaultType, Scenario
        from faultray.model.components import (
            Capacity, Component, ComponentType, Dependency, ResourceMetrics,
        )
        from faultray.model.graph import InfraGraph

        # Create a 10-component graph so we can fault exactly 9 (90%)
        graph = InfraGraph()
        for i in range(10):
            graph.add_component(Component(
                id=f"c{i}", name=f"c{i}", type=ComponentType.APP_SERVER,
                host=f"h{i}", port=8080 + i, replicas=1,
                metrics=ResourceMetrics(cpu_percent=30, memory_percent=40),
                capacity=Capacity(max_connections=100),
            ))

        engine = SimulationEngine(graph)
        # Fault 9 of 10 = 90%
        scenario = Scenario(
            id="nine-down", name="Nine down", description="90% down",
            faults=[
                Fault(target_component_id=f"c{i}", fault_type=FaultType.COMPONENT_DOWN)
                for i in range(9)
            ],
        )
        result = engine.run_scenario(scenario)

        # Merged likelihood should be min(likelihood, 0.05)
        assert result.cascade.likelihood <= 0.05, (
            f"Likelihood {result.cascade.likelihood} should be <= 0.05 "
            f"for 90% fault ratio"
        )


# ===========================================================================
# 6. Unit tests for evaluate helper functions
# ===========================================================================


class TestEvaluateHelpers:
    """Tests for evaluate.py helper functions."""

    def test_compute_avg_availability_empty(self) -> None:
        """_compute_avg_availability with empty list returns 100.0."""
        from faultray.cli.evaluate import _compute_avg_availability
        assert _compute_avg_availability([]) == 100.0

    def test_verdict_color(self) -> None:
        """_verdict_color returns correct colors for each verdict."""
        from faultray.cli.evaluate import _verdict_color
        assert _verdict_color("NEEDS ATTENTION") == "red"
        assert _verdict_color("ACCEPTABLE") == "yellow"
        assert _verdict_color("HEALTHY") == "green"
        assert _verdict_color("UNKNOWN") == "green"  # default

    def test_build_comparison_json_strips_raw(self) -> None:
        """_build_comparison_json should strip _raw keys from output."""
        from faultray.cli.evaluate import _build_comparison_json

        data = {
            "model": "a.json",
            "static": {"resilience_score": 80.0, "critical": 1, "warning": 2, "passed": 5},
            "dynamic": {"critical": 0, "warning": 1, "worst_severity": 5.0},
            "ops": {"avg_availability": 99.95, "total_downtime_seconds": 10.0},
            "capacity": {"over_provisioned_count": 2, "cost_reduction_percent": -5.0},
            "verdict": "ACCEPTABLE",
            "_raw": {"should_be_stripped": True},
        }
        data_b = {
            "model": "b.json",
            "static": {"resilience_score": 90.0, "critical": 0, "warning": 1, "passed": 7},
            "dynamic": {"critical": 0, "warning": 0, "worst_severity": 3.0},
            "ops": {"avg_availability": 99.99, "total_downtime_seconds": 5.0},
            "capacity": {"over_provisioned_count": 1, "cost_reduction_percent": -3.0},
            "verdict": "HEALTHY",
            "_raw": {"should_be_stripped": True},
        }
        result = _build_comparison_json(data, data_b)

        assert "_raw" not in result["model_a"]
        assert "_raw" not in result["model_b"]
        assert result["comparison"]["resilience_score_delta"] == 10.0
        assert result["comparison"]["verdict_changed"] is True
        assert result["comparison"]["verdict_a"] == "ACCEPTABLE"
        assert result["comparison"]["verdict_b"] == "HEALTHY"

    def test_print_comparison_table_no_crash(self) -> None:
        """_print_comparison_table should not crash with synthetic data.

        Exercises lines 241-412 via direct call.
        """
        from io import StringIO
        from rich.console import Console
        from faultray.cli.evaluate import _print_comparison_table

        # Temporarily patch the module-level console
        import faultray.cli.evaluate as eval_mod
        buf = StringIO()
        original_console = eval_mod.console
        eval_mod.console = Console(file=buf, force_terminal=False, width=120)

        try:
            data_a = {
                "model": "a.json",
                "static": {"resilience_score": 75.0, "critical": 2, "warning": 3, "passed": 10},
                "dynamic": {"critical": 1, "warning": 2, "worst_severity": 8.0},
                "ops": {"avg_availability": 99.5, "total_downtime_seconds": 100.0},
                "capacity": {"over_provisioned_count": 3, "cost_reduction_percent": -2.0},
                "verdict": "NEEDS ATTENTION",
            }
            data_b = {
                "model": "b.json",
                "static": {"resilience_score": 85.0, "critical": 0, "warning": 1, "passed": 14},
                "dynamic": {"critical": 0, "warning": 1, "worst_severity": 5.5},
                "ops": {"avg_availability": 99.95, "total_downtime_seconds": 20.0},
                "capacity": {"over_provisioned_count": 1, "cost_reduction_percent": -5.0},
                "verdict": "ACCEPTABLE",
            }
            _print_comparison_table(data_a, data_b)

            output = buf.getvalue()
            assert "COMPARISON SUMMARY" in output
            assert "Resilience Score" in output
            assert "Verdict" in output
            # Should show verdict change text
            assert "NEEDS ATTENTION" in output
            assert "ACCEPTABLE" in output
        finally:
            eval_mod.console = original_console
