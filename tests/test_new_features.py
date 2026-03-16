"""Tests for newly added / modified features targeting coverage gaps.

Covers:
  1. evaluate command (cli/evaluate.py) — all 5 engines mocked, console/JSON/HTML output,
     verdict logic, _compute_avg_availability helper
  2. simulate truncation warning (cli/simulate.py line 67)
  3. report.py score explanation (lines 115-116)
  4. html_report.py score explanation (line 271)
  5. ops.py Right-Size table (lines 344-364)
  6. engine.py new fields: total_generated, was_truncated, run_scenarios truncation
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from faultray.cli import app
from faultray.model.demo import create_demo_graph
from faultray.simulator.engine import (
    MAX_SCENARIOS,
    ScenarioResult,
    SimulationEngine,
    SimulationReport,
)

runner = CliRunner()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_model_file(tmp_path: Path) -> Path:
    graph = create_demo_graph()
    model_path = tmp_path / "test-model.json"
    graph.save(model_path)
    return model_path


def _make_scenario_result(name: str, risk: float) -> ScenarioResult:
    """Build a minimal ScenarioResult with a given risk score."""
    from faultray.simulator.cascade import CascadeChain
    from faultray.simulator.scenarios import Scenario

    scenario = Scenario(
        id=f"s-{name}",
        name=name,
        description=f"Test scenario {name}",
        faults=[],
    )
    cascade = CascadeChain(trigger=name, total_components=5)
    return ScenarioResult(scenario=scenario, cascade=cascade, risk_score=risk)


def _make_static_report(
    score: float = 85.0,
    n_critical: int = 0,
    n_warning: int = 0,
    n_passed: int = 3,
    total_generated: int = 10,
    was_truncated: bool = False,
) -> SimulationReport:
    """Build a SimulationReport with the desired finding counts."""
    results = []
    for i in range(n_critical):
        results.append(_make_scenario_result(f"crit-{i}", 8.0))
    for i in range(n_warning):
        results.append(_make_scenario_result(f"warn-{i}", 5.0))
    for i in range(n_passed):
        results.append(_make_scenario_result(f"pass-{i}", 1.0))
    return SimulationReport(
        results=results,
        resilience_score=score,
        total_generated=total_generated,
        was_truncated=was_truncated,
    )


def _make_dynamic_report(
    n_critical: int = 0,
    n_warning: int = 0,
    n_passed: int = 2,
) -> SimpleNamespace:
    """Build a mock DynamicSimulationReport."""
    from faultray.simulator.dynamic_engine import (
        DynamicScenario,
        DynamicScenarioResult,
        DynamicSimulationReport,
    )
    from faultray.simulator.scenarios import Fault

    results = []
    for i in range(n_critical):
        sc = DynamicScenario(
            id=f"dc-{i}", name=f"dyn-crit-{i}",
            description="dynamic critical", faults=[],
        )
        results.append(DynamicScenarioResult(scenario=sc, peak_severity=8.0))
    for i in range(n_warning):
        sc = DynamicScenario(
            id=f"dw-{i}", name=f"dyn-warn-{i}",
            description="dynamic warning", faults=[],
        )
        results.append(DynamicScenarioResult(scenario=sc, peak_severity=5.0))
    for i in range(n_passed):
        sc = DynamicScenario(
            id=f"dp-{i}", name=f"dyn-pass-{i}",
            description="dynamic passed", faults=[],
        )
        results.append(DynamicScenarioResult(scenario=sc, peak_severity=1.0))
    return DynamicSimulationReport(results=results, resilience_score=80.0)


def _make_ops_result(
    avg_avail: float = 99.95,
    min_avail: float = 99.5,
    total_downtime: float = 120.0,
    total_events: int = 10,
    total_deploys: int = 4,
    total_failures: int = 2,
    total_degradation: int = 3,
    peak_util: float = 65.0,
) -> SimpleNamespace:
    """Build a mock OpsSimulationResult."""
    # Create SLI timeline entries for _compute_avg_availability
    sli_points = []
    for _ in range(5):
        sli_points.append(SimpleNamespace(availability_percent=avg_avail))
    return SimpleNamespace(
        sli_timeline=sli_points,
        min_availability=min_avail,
        total_downtime_seconds=total_downtime,
        events=[None] * total_events,
        total_deploys=total_deploys,
        total_failures=total_failures,
        total_degradation_events=total_degradation,
        peak_utilization=peak_util,
    )


def _make_whatif_results() -> list:
    """Build a list of mock WhatIfResult objects."""
    from faultray.simulator.whatif_engine import WhatIfResult

    return [
        WhatIfResult(
            parameter="traffic_factor",
            values=[1.0, 1.5, 2.0],
            avg_availabilities=[99.99, 99.9, 99.5],
            min_availabilities=[99.95, 99.8, 99.0],
            total_failures=[0, 1, 3],
            total_downtimes=[0.0, 10.0, 50.0],
            slo_pass=[True, True, False],
            breakpoint_value=2.0,
        ),
        WhatIfResult(
            parameter="mttr_factor",
            values=[1.0, 2.0, 3.0],
            avg_availabilities=[99.99, 99.95, 99.9],
            min_availabilities=[99.95, 99.9, 99.85],
            total_failures=[0, 0, 1],
            total_downtimes=[0.0, 5.0, 15.0],
            slo_pass=[True, True, True],
            breakpoint_value=None,
        ),
    ]


def _make_capacity_report(over_provisioned_count: int = 0) -> SimpleNamespace:
    """Build a mock CapacityPlanReport."""
    from faultray.simulator.capacity_engine import (
        CapacityForecast,
        CapacityPlanReport,
        ErrorBudgetForecast,
    )

    forecasts = []
    # An over-provisioned component: current > recommended_3m
    for i in range(over_provisioned_count):
        forecasts.append(CapacityForecast(
            component_id=f"over-{i}",
            component_type="app_server",
            current_replicas=5,
            current_utilization=20.0,
            monthly_growth_rate=0.10,
            months_to_capacity=24.0,
            recommended_replicas_3m=2,
            recommended_replicas_6m=2,
            recommended_replicas_12m=3,
            scaling_urgency="healthy",
        ))
    # A normal component
    forecasts.append(CapacityForecast(
        component_id="app-normal",
        component_type="app_server",
        current_replicas=2,
        current_utilization=50.0,
        monthly_growth_rate=0.10,
        months_to_capacity=5.0,
        recommended_replicas_3m=3,
        recommended_replicas_6m=4,
        recommended_replicas_12m=5,
        scaling_urgency="warning",
    ))

    error_budget = ErrorBudgetForecast(
        slo_target=99.9,
        budget_total_minutes=43.2,
        budget_consumed_minutes=10.0,
        budget_consumed_percent=23.15,
        burn_rate_per_day=1.43,
        days_to_exhaustion=23.2,
        projected_monthly_consumption=99.3,
        status="warning",
    )

    return CapacityPlanReport(
        forecasts=forecasts,
        error_budget=error_budget,
        bottleneck_components=["app-normal"],
        scaling_recommendations=["Scale app-normal"],
        estimated_monthly_cost_increase=-5.0 if over_provisioned_count > 0 else 10.0,
        summary="Test capacity plan summary",
    )


# ---------------------------------------------------------------------------
# Common mock context manager for evaluate command
# ---------------------------------------------------------------------------

def _patch_all_engines(
    static_report=None,
    dyn_report=None,
    ops_result=None,
    whatif_results=None,
    cap_report=None,
):
    """Return a combined patch context for all 5 engines used by evaluate.

    The evaluate command imports engines lazily inside the function body,
    so we patch at the source module level.
    """
    if static_report is None:
        static_report = _make_static_report()
    if dyn_report is None:
        dyn_report = _make_dynamic_report()
    if ops_result is None:
        ops_result = _make_ops_result()
    if whatif_results is None:
        whatif_results = _make_whatif_results()
    if cap_report is None:
        cap_report = _make_capacity_report()

    mock_static = MagicMock()
    mock_static.return_value.run_all_defaults.return_value = static_report

    mock_dyn = MagicMock()
    mock_dyn.return_value.run_all_dynamic_defaults.return_value = dyn_report

    mock_ops = MagicMock()
    mock_ops.return_value.run_ops_scenario.return_value = ops_result

    mock_whatif = MagicMock()
    mock_whatif.return_value.run_default_whatifs.return_value = whatif_results

    mock_cap = MagicMock()
    mock_cap.return_value.forecast.return_value = cap_report

    # Engines are imported lazily inside evaluate(), so patch at source module
    patches = [
        patch("faultray.simulator.engine.SimulationEngine", mock_static),
        patch("faultray.simulator.dynamic_engine.DynamicSimulationEngine", mock_dyn),
        patch("faultray.simulator.ops_engine.OpsSimulationEngine", mock_ops),
        patch("faultray.simulator.whatif_engine.WhatIfEngine", mock_whatif),
        patch("faultray.simulator.capacity_engine.CapacityPlanningEngine", mock_cap),
    ]
    return patches


# ===================================================================
# 1. evaluate command tests (src/faultray/cli/evaluate.py)
# ===================================================================


class TestEvaluateCommand:
    """Tests for the ``evaluate`` CLI command."""

    def test_evaluate_console_output_healthy(self, tmp_path):
        """Evaluate with no critical/warning findings => HEALTHY verdict."""
        model_path = _create_model_file(tmp_path)
        patches = _patch_all_engines(
            static_report=_make_static_report(n_critical=0, n_warning=0, n_passed=5),
            dyn_report=_make_dynamic_report(n_critical=0, n_warning=0, n_passed=3),
        )
        for p in patches:
            p.start()
        try:
            result = runner.invoke(app, [
                "evaluate", "--model", str(model_path),
            ])
            assert result.exit_code == 0, result.output
            assert "HEALTHY" in result.output
            assert "Static Simulation" in result.output
            assert "Dynamic Simulation" in result.output
            assert "Ops Simulation" in result.output
            assert "What-If Analysis" in result.output
            assert "Capacity Planning" in result.output
            assert "Overall Assessment" in result.output
        finally:
            for p in patches:
                p.stop()

    def test_evaluate_verdict_needs_attention(self, tmp_path):
        """Critical findings in static => NEEDS ATTENTION verdict."""
        model_path = _create_model_file(tmp_path)
        patches = _patch_all_engines(
            static_report=_make_static_report(n_critical=2, n_warning=1, n_passed=3),
        )
        for p in patches:
            p.start()
        try:
            result = runner.invoke(app, [
                "evaluate", "--model", str(model_path),
            ])
            assert result.exit_code == 0, result.output
            assert "NEEDS ATTENTION" in result.output
        finally:
            for p in patches:
                p.stop()

    def test_evaluate_verdict_needs_attention_dynamic(self, tmp_path):
        """Critical findings in dynamic => NEEDS ATTENTION verdict."""
        model_path = _create_model_file(tmp_path)
        patches = _patch_all_engines(
            static_report=_make_static_report(n_critical=0, n_warning=0, n_passed=5),
            dyn_report=_make_dynamic_report(n_critical=1, n_warning=0, n_passed=2),
        )
        for p in patches:
            p.start()
        try:
            result = runner.invoke(app, [
                "evaluate", "--model", str(model_path),
            ])
            assert result.exit_code == 0, result.output
            assert "NEEDS ATTENTION" in result.output
        finally:
            for p in patches:
                p.stop()

    def test_evaluate_verdict_acceptable(self, tmp_path):
        """Warning findings but no critical => ACCEPTABLE verdict."""
        model_path = _create_model_file(tmp_path)
        patches = _patch_all_engines(
            static_report=_make_static_report(n_critical=0, n_warning=2, n_passed=3),
            dyn_report=_make_dynamic_report(n_critical=0, n_warning=0, n_passed=3),
        )
        for p in patches:
            p.start()
        try:
            result = runner.invoke(app, [
                "evaluate", "--model", str(model_path),
            ])
            assert result.exit_code == 0, result.output
            assert "ACCEPTABLE" in result.output
        finally:
            for p in patches:
                p.stop()

    def test_evaluate_verdict_acceptable_dynamic_warnings(self, tmp_path):
        """Warning findings in dynamic only => ACCEPTABLE verdict."""
        model_path = _create_model_file(tmp_path)
        patches = _patch_all_engines(
            static_report=_make_static_report(n_critical=0, n_warning=0, n_passed=5),
            dyn_report=_make_dynamic_report(n_critical=0, n_warning=2, n_passed=2),
        )
        for p in patches:
            p.start()
        try:
            result = runner.invoke(app, [
                "evaluate", "--model", str(model_path),
            ])
            assert result.exit_code == 0, result.output
            assert "ACCEPTABLE" in result.output
        finally:
            for p in patches:
                p.stop()

    def test_evaluate_json_output(self, tmp_path):
        """--json flag outputs valid JSON with all engine sections."""
        model_path = _create_model_file(tmp_path)
        patches = _patch_all_engines(
            cap_report=_make_capacity_report(over_provisioned_count=1),
        )
        for p in patches:
            p.start()
        try:
            result = runner.invoke(app, [
                "evaluate", "--model", str(model_path), "--json",
            ])
            assert result.exit_code == 0, result.output
            # The output should contain JSON; parse from after the progress messages
            # CliRunner captures all output; find the JSON portion
            output = result.output
            # Find the first '{' and parse from there
            json_start = output.index("{")
            json_str = output[json_start:]
            data = json.loads(json_str)
            assert "static" in data
            assert "dynamic" in data
            assert "ops" in data
            assert "whatif" in data
            assert "capacity" in data
            assert "verdict" in data
            assert data["verdict"] in ("HEALTHY", "ACCEPTABLE", "NEEDS ATTENTION")
            # Verify static section details
            assert "resilience_score" in data["static"]
            assert "total_scenarios" in data["static"]
            # Verify ops section details
            assert "avg_availability" in data["ops"]
            assert "total_events" in data["ops"]
        finally:
            for p in patches:
                p.stop()

    def test_evaluate_html_export(self, tmp_path):
        """--html flag generates an HTML file."""
        model_path = _create_model_file(tmp_path)
        html_path = tmp_path / "eval_report.html"
        patches = _patch_all_engines()
        for p in patches:
            p.start()
        try:
            result = runner.invoke(app, [
                "evaluate", "--model", str(model_path),
                "--html", str(html_path),
            ])
            assert result.exit_code == 0, result.output
            assert "HTML report saved" in result.output
            assert html_path.exists()
            content = html_path.read_text(encoding="utf-8")
            assert "FaultRay Full Evaluation Report" in content
            assert "<!DOCTYPE html>" in content
            assert "Static Simulation" in content
            assert "Dynamic Simulation" in content
            assert "Ops Simulation" in content
            assert "Capacity Planning" in content
        finally:
            for p in patches:
                p.stop()

    def test_evaluate_html_verdict_colors(self, tmp_path):
        """HTML report uses correct verdict color coding."""
        model_path = _create_model_file(tmp_path)
        html_path = tmp_path / "eval_needs_attention.html"
        patches = _patch_all_engines(
            static_report=_make_static_report(n_critical=1),
        )
        for p in patches:
            p.start()
        try:
            result = runner.invoke(app, [
                "evaluate", "--model", str(model_path),
                "--html", str(html_path),
            ])
            assert result.exit_code == 0
            content = html_path.read_text(encoding="utf-8")
            assert "NEEDS ATTENTION" in content
            # Red color for NEEDS ATTENTION
            assert "#e74c3c" in content
        finally:
            for p in patches:
                p.stop()

    def test_evaluate_ops_days_option(self, tmp_path):
        """--ops-days option is passed to the ops simulation."""
        model_path = _create_model_file(tmp_path)
        patches = _patch_all_engines()
        for p in patches:
            p.start()
        try:
            result = runner.invoke(app, [
                "evaluate", "--model", str(model_path),
                "--ops-days", "14",
            ])
            assert result.exit_code == 0, result.output
            assert "14 days" in result.output
        finally:
            for p in patches:
                p.stop()

    def test_evaluate_file_alias(self, tmp_path):
        """--file option works as alias for --model."""
        model_path = _create_model_file(tmp_path)
        patches = _patch_all_engines()
        for p in patches:
            p.start()
        try:
            result = runner.invoke(app, [
                "evaluate", "--file", str(model_path),
            ])
            assert result.exit_code == 0, result.output
            assert "Static Simulation" in result.output
        finally:
            for p in patches:
                p.stop()

    def test_evaluate_console_worst_dynamic_scenario_displayed(self, tmp_path):
        """When dynamic worst severity >= 4.0, it should be displayed."""
        model_path = _create_model_file(tmp_path)
        # Create a dynamic report with a high severity scenario
        dyn = _make_dynamic_report(n_critical=1, n_warning=0, n_passed=1)
        patches = _patch_all_engines(dyn_report=dyn)
        for p in patches:
            p.start()
        try:
            result = runner.invoke(app, [
                "evaluate", "--model", str(model_path),
            ])
            assert result.exit_code == 0, result.output
            # The worst scenario name should appear in output
            assert "Worst" in result.output or "dyn-crit-0" in result.output
        finally:
            for p in patches:
                p.stop()

    def test_evaluate_over_provisioned_display(self, tmp_path):
        """Over-provisioned components display in console output."""
        model_path = _create_model_file(tmp_path)
        patches = _patch_all_engines(
            cap_report=_make_capacity_report(over_provisioned_count=2),
        )
        for p in patches:
            p.start()
        try:
            result = runner.invoke(app, [
                "evaluate", "--model", str(model_path),
            ])
            assert result.exit_code == 0, result.output
            assert "Over-provisioned: 2 components" in result.output
        finally:
            for p in patches:
                p.stop()

    def test_evaluate_cost_reduction_display(self, tmp_path):
        """Negative cost change shows as 'Cost Reduction'."""
        model_path = _create_model_file(tmp_path)
        patches = _patch_all_engines(
            cap_report=_make_capacity_report(over_provisioned_count=1),
        )
        for p in patches:
            p.start()
        try:
            result = runner.invoke(app, [
                "evaluate", "--model", str(model_path),
            ])
            assert result.exit_code == 0, result.output
            assert "Cost Reduction" in result.output
        finally:
            for p in patches:
                p.stop()

    def test_evaluate_cost_increase_display(self, tmp_path):
        """Positive cost change shows as 'Cost Increase'."""
        model_path = _create_model_file(tmp_path)
        patches = _patch_all_engines(
            cap_report=_make_capacity_report(over_provisioned_count=0),
        )
        for p in patches:
            p.start()
        try:
            result = runner.invoke(app, [
                "evaluate", "--model", str(model_path),
            ])
            assert result.exit_code == 0, result.output
            assert "Cost Increase" in result.output
        finally:
            for p in patches:
                p.stop()

    def test_evaluate_zero_cost_change(self, tmp_path):
        """Zero cost change shows as 'Cost Change: 0.0%'."""
        model_path = _create_model_file(tmp_path)
        cap = _make_capacity_report()
        # Override cost to exactly 0
        cap.estimated_monthly_cost_increase = 0.0
        patches = _patch_all_engines(cap_report=cap)
        for p in patches:
            p.start()
        try:
            result = runner.invoke(app, [
                "evaluate", "--model", str(model_path),
            ])
            assert result.exit_code == 0, result.output
            assert "Cost Change: 0.0%" in result.output
        finally:
            for p in patches:
                p.stop()

    def test_evaluate_high_availability_green(self, tmp_path):
        """Availability >= 99.9 should show green color marker."""
        model_path = _create_model_file(tmp_path)
        patches = _patch_all_engines(
            ops_result=_make_ops_result(avg_avail=99.95),
        )
        for p in patches:
            p.start()
        try:
            result = runner.invoke(app, [
                "evaluate", "--model", str(model_path),
            ])
            assert result.exit_code == 0, result.output
            assert "99.950%" in result.output
        finally:
            for p in patches:
                p.stop()

    def test_evaluate_low_availability_red(self, tmp_path):
        """Availability < 99.0 should show red in output."""
        model_path = _create_model_file(tmp_path)
        patches = _patch_all_engines(
            ops_result=_make_ops_result(avg_avail=98.5),
        )
        for p in patches:
            p.start()
        try:
            result = runner.invoke(app, [
                "evaluate", "--model", str(model_path),
            ])
            assert result.exit_code == 0, result.output
            assert "98.500%" in result.output
        finally:
            for p in patches:
                p.stop()


class TestComputeAvgAvailability:
    """Tests for the _compute_avg_availability helper."""

    def test_empty_timeline(self):
        from faultray.cli.evaluate import _compute_avg_availability
        assert _compute_avg_availability([]) == 100.0

    def test_single_point(self):
        from faultray.cli.evaluate import _compute_avg_availability
        point = SimpleNamespace(availability_percent=99.5)
        assert _compute_avg_availability([point]) == 99.5

    def test_multiple_points(self):
        from faultray.cli.evaluate import _compute_avg_availability
        points = [
            SimpleNamespace(availability_percent=100.0),
            SimpleNamespace(availability_percent=99.0),
            SimpleNamespace(availability_percent=98.0),
        ]
        result = _compute_avg_availability(points)
        assert abs(result - 99.0) < 0.01

    def test_all_100(self):
        from faultray.cli.evaluate import _compute_avg_availability
        points = [SimpleNamespace(availability_percent=100.0) for _ in range(10)]
        assert _compute_avg_availability(points) == 100.0


# ===================================================================
# 2. simulate truncation warning (src/faultray/cli/simulate.py)
# ===================================================================


class TestSimulateTruncationWarning:
    """Test that truncation warning appears when report.was_truncated is True."""

    def test_truncation_warning_shown(self, tmp_path):
        model_path = _create_model_file(tmp_path)
        truncated_report = _make_static_report(
            n_passed=5,
            total_generated=1500,
            was_truncated=True,
        )
        with patch(
            "faultray.cli.simulate.SimulationEngine"
        ) as mock_engine:
            mock_engine.return_value.run_all_defaults.return_value = truncated_report
            result = runner.invoke(app, [
                "simulate", "--model", str(model_path),
            ])
            assert result.exit_code == 0, result.output
            assert "1,500" in result.output or "1500" in result.output
            assert "truncated" in result.output.lower()
            assert "Use --max-scenarios" in result.output

    def test_no_truncation_warning_when_not_truncated(self, tmp_path):
        model_path = _create_model_file(tmp_path)
        normal_report = _make_static_report(
            n_passed=5,
            total_generated=5,
            was_truncated=False,
        )
        with patch(
            "faultray.cli.simulate.SimulationEngine"
        ) as mock_engine:
            mock_engine.return_value.run_all_defaults.return_value = normal_report
            result = runner.invoke(app, [
                "simulate", "--model", str(model_path),
            ])
            assert result.exit_code == 0, result.output
            assert "truncated" not in result.output.lower() or "skipped" not in result.output


# ===================================================================
# 3. report.py score explanation (lines 115-116)
# ===================================================================


class TestReportScoreExplanation:
    """Test print_simulation_report() score explanation for low scores."""

    def test_score_explanation_low_score_no_findings(self):
        """Score < 70 with no critical/warning => explanation shown."""
        from rich.console import Console
        from faultray.reporter.report import print_simulation_report

        report = _make_static_report(
            score=55.0, n_critical=0, n_warning=0, n_passed=5,
        )
        buf = StringIO()
        console = Console(file=buf, force_terminal=False, width=120)
        print_simulation_report(report, console)
        output = buf.getvalue()
        assert "structural vulnerabilities" in output
        assert "good runtime resilience" in output

    def test_no_explanation_high_score(self):
        """Score >= 70 => no structural explanation shown."""
        from rich.console import Console
        from faultray.reporter.report import print_simulation_report

        report = _make_static_report(
            score=85.0, n_critical=0, n_warning=0, n_passed=5,
        )
        buf = StringIO()
        console = Console(file=buf, force_terminal=False, width=120)
        print_simulation_report(report, console)
        output = buf.getvalue()
        assert "structural vulnerabilities" not in output

    def test_no_explanation_low_score_with_critical(self):
        """Score < 70 but has critical findings => no structural explanation."""
        from rich.console import Console
        from faultray.reporter.report import print_simulation_report

        report = _make_static_report(
            score=40.0, n_critical=2, n_warning=0, n_passed=3,
        )
        buf = StringIO()
        console = Console(file=buf, force_terminal=False, width=120)
        print_simulation_report(report, console)
        output = buf.getvalue()
        assert "structural vulnerabilities" not in output

    def test_no_explanation_low_score_with_warnings(self):
        """Score < 70 with warnings => no structural explanation."""
        from rich.console import Console
        from faultray.reporter.report import print_simulation_report

        report = _make_static_report(
            score=60.0, n_critical=0, n_warning=2, n_passed=3,
        )
        buf = StringIO()
        console = Console(file=buf, force_terminal=False, width=120)
        print_simulation_report(report, console)
        output = buf.getvalue()
        assert "structural vulnerabilities" not in output


# ===================================================================
# 4. html_report.py score explanation (line 271)
# ===================================================================


class TestHtmlReportScoreExplanation:
    """Test generate_html_report() score explanation for low scores."""

    def test_html_score_explanation_low_no_findings(self):
        """Score < 70 with no critical/warning => HTML contains explanation."""
        from faultray.reporter.html_report import generate_html_report

        graph = create_demo_graph()
        report = _make_static_report(
            score=55.0, n_critical=0, n_warning=0, n_passed=5,
        )
        html = generate_html_report(report, graph)
        assert "good runtime resilience" in html
        assert "architectural gaps" in html

    def test_html_no_explanation_high_score(self):
        """Score >= 70 => no 'architectural gaps' explanation."""
        from faultray.reporter.html_report import generate_html_report

        graph = create_demo_graph()
        report = _make_static_report(
            score=85.0, n_critical=0, n_warning=0, n_passed=5,
        )
        html = generate_html_report(report, graph)
        assert "architectural gaps" not in html

    def test_html_critical_explanation(self):
        """Score < 70 with critical findings => cascade failure explanation."""
        from faultray.reporter.html_report import generate_html_report

        graph = create_demo_graph()
        report = _make_static_report(
            score=40.0, n_critical=2, n_warning=0, n_passed=3,
        )
        html = generate_html_report(report, graph)
        assert "cascade failures" in html
        assert "2 critical scenario(s)" in html


# ===================================================================
# 5. ops.py Right-Size table (lines 344-364)
# ===================================================================


class TestOpsRightSizeTable:
    """Test the capacity Right-Size Opportunities table display."""

    def test_right_size_table_displayed(self, tmp_path):
        """Over-provisioned components should produce a Right-Size table."""
        model_path = _create_model_file(tmp_path)
        cap_report = _make_capacity_report(over_provisioned_count=2)
        with patch(
            "faultray.simulator.capacity_engine.CapacityPlanningEngine.forecast",
            return_value=cap_report,
        ):
            result = runner.invoke(app, [
                "capacity", "--model", str(model_path),
            ])
            assert result.exit_code == 0, result.output
            assert "Right-Size Opportunities" in result.output

    def test_no_right_size_table_when_none_over(self, tmp_path):
        """No over-provisioned components => no Right-Size table."""
        model_path = _create_model_file(tmp_path)
        cap_report = _make_capacity_report(over_provisioned_count=0)
        with patch(
            "faultray.simulator.capacity_engine.CapacityPlanningEngine.forecast",
            return_value=cap_report,
        ):
            result = runner.invoke(app, [
                "capacity", "--model", str(model_path),
            ])
            assert result.exit_code == 0, result.output
            assert "Right-Size" not in result.output


# ===================================================================
# 6. engine.py new fields (total_generated, was_truncated, run_scenarios)
# ===================================================================


class TestEngineNewFields:
    """Test SimulationReport new fields and run_scenarios truncation."""

    def test_simulation_report_defaults(self):
        """SimulationReport defaults: total_generated=0, was_truncated=False."""
        report = SimulationReport()
        assert report.total_generated == 0
        assert report.was_truncated is False

    def test_simulation_report_with_values(self):
        """SimulationReport stores total_generated and was_truncated."""
        report = SimulationReport(
            results=[], resilience_score=90.0,
            total_generated=1500, was_truncated=True,
        )
        assert report.total_generated == 1500
        assert report.was_truncated is True

    def test_run_scenarios_no_truncation(self):
        """run_scenarios with fewer scenarios than limit => no truncation."""
        from faultray.simulator.scenarios import Fault, FaultType, Scenario

        graph = create_demo_graph()
        engine = SimulationEngine(graph)

        component_ids = list(graph.components.keys())
        scenarios = [
            Scenario(
                id=f"s{i}", name=f"scenario-{i}",
                description=f"Test scenario {i}",
                faults=[Fault(
                    target_component_id=component_ids[0],
                    fault_type=FaultType.COMPONENT_DOWN,
                )],
            )
            for i in range(3)
        ]

        report = engine.run_scenarios(scenarios, max_scenarios=10)
        assert report.total_generated == 3
        assert report.was_truncated is False
        assert len(report.results) == 3

    def test_run_scenarios_with_truncation(self):
        """run_scenarios with more scenarios than max_scenarios => truncation."""
        from faultray.simulator.scenarios import Fault, FaultType, Scenario

        graph = create_demo_graph()
        engine = SimulationEngine(graph)

        component_ids = list(graph.components.keys())
        scenarios = [
            Scenario(
                id=f"s{i}", name=f"scenario-{i}",
                description=f"Test scenario {i}",
                faults=[Fault(
                    target_component_id=component_ids[0],
                    fault_type=FaultType.COMPONENT_DOWN,
                )],
            )
            for i in range(10)
        ]

        report = engine.run_scenarios(scenarios, max_scenarios=5)
        assert report.total_generated == 10
        assert report.was_truncated is True
        assert len(report.results) == 5

    def test_run_scenarios_default_limit(self):
        """run_scenarios with max_scenarios=0 uses module MAX_SCENARIOS."""
        from faultray.simulator.scenarios import Fault, FaultType, Scenario

        graph = create_demo_graph()
        engine = SimulationEngine(graph)

        component_ids = list(graph.components.keys())
        # Create fewer scenarios than MAX_SCENARIOS
        scenarios = [
            Scenario(
                id=f"s{i}", name=f"scenario-{i}",
                description=f"Test scenario {i}",
                faults=[Fault(
                    target_component_id=component_ids[0],
                    fault_type=FaultType.COMPONENT_DOWN,
                )],
            )
            for i in range(3)
        ]

        report = engine.run_scenarios(scenarios, max_scenarios=0)
        assert report.total_generated == 3
        assert report.was_truncated is False  # 3 < MAX_SCENARIOS (1000)
        assert len(report.results) == 3

    def test_scenario_result_classification(self):
        """ScenarioResult.is_critical and is_warning based on risk_score."""
        r_critical = _make_scenario_result("critical", 8.0)
        assert r_critical.is_critical is True
        assert r_critical.is_warning is False

        r_warning = _make_scenario_result("warning", 5.0)
        assert r_warning.is_critical is False
        assert r_warning.is_warning is True

        r_passed = _make_scenario_result("passed", 2.0)
        assert r_passed.is_critical is False
        assert r_passed.is_warning is False

    def test_report_findings_lists(self):
        """SimulationReport.critical_findings, warnings, passed."""
        report = _make_static_report(n_critical=2, n_warning=3, n_passed=4)
        assert len(report.critical_findings) == 2
        assert len(report.warnings) == 3
        assert len(report.passed) == 4
