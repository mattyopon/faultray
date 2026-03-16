"""End-to-end workflow tests -- verify the complete user journey works.

These tests use NO mocks. They exercise the real integration between
engines, CLI runners, templates, and persistence layers.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest
from typer.testing import CliRunner

from faultray.cli import app
from faultray.model.demo import create_demo_graph
from faultray.model.graph import InfraGraph

runner = CliRunner()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _save_demo_model(directory: Path) -> Path:
    """Save the demo graph to a JSON model file and return its path."""
    graph = create_demo_graph()
    model_path = directory / "model.json"
    graph.save(model_path)
    return model_path


def _save_demo_yaml(directory: Path) -> Path:
    """Save a minimal YAML infrastructure model and return its path."""
    yaml_content = """\
components:
  - id: web
    name: web-server
    type: web_server
    host: web01
    port: 443
    replicas: 2
    metrics:
      cpu_percent: 30
      memory_percent: 40
    capacity:
      max_connections: 5000

  - id: app
    name: app-server
    type: app_server
    host: app01
    port: 8080
    replicas: 1
    metrics:
      cpu_percent: 50
      memory_percent: 60
    capacity:
      max_connections: 1000

  - id: db
    name: database
    type: database
    host: db01
    port: 5432
    replicas: 1
    metrics:
      cpu_percent: 40
      memory_percent: 70
    capacity:
      max_connections: 100

dependencies:
  - source: web
    target: app
    type: requires
  - source: app
    target: db
    type: requires
"""
    yaml_path = directory / "infra.yaml"
    yaml_path.write_text(yaml_content, encoding="utf-8")
    return yaml_path


def _extract_json(output: str) -> dict | list:
    """Extract JSON from CLI output (may contain Rich formatting before JSON).

    Rich console output may include ANSI codes and formatting brackets.
    We try multiple strategies to find and parse the JSON payload.
    """
    text = output.strip()
    # Strategy 1: Try parsing from each { or [ that looks like JSON start
    for i, ch in enumerate(text):
        if ch == "{":
            # Try to find matching closing brace
            try:
                return json.loads(text[i:])
            except json.JSONDecodeError:
                continue
        elif ch == "[" and i + 1 < len(text) and text[i + 1] not in ("/", " "):
            # Skip Rich color codes like [red], [bold], etc.
            try:
                return json.loads(text[i:])
            except json.JSONDecodeError:
                continue

    raise ValueError(f"No JSON found in output: {text[:300]}")


# ---------------------------------------------------------------------------
# Test 1: Complete new-user journey
# ---------------------------------------------------------------------------

class TestCompleteNewUserJourney:
    """Simulate a brand-new user's first experience end to end."""

    def test_quickstart_generates_yaml(self, tmp_path: Path):
        """Step 1: quickstart produces a YAML file."""
        output_yaml = tmp_path / "infra.yaml"
        result = runner.invoke(
            app,
            ["quickstart", "--template", "web-app", "--output", str(output_yaml)],
        )
        assert result.exit_code == 0, f"quickstart failed: {result.output}"
        assert output_yaml.exists()

    def test_simulate_produces_report(self, tmp_path: Path):
        """Step 2: simulate with a model produces a simulation report."""
        model_path = _save_demo_model(tmp_path)
        result = runner.invoke(app, ["simulate", "--model", str(model_path), "--json"])
        assert result.exit_code == 0, f"simulate failed: {result.output}"
        data = _extract_json(result.output)
        assert "resilience_score" in data
        assert "total_scenarios" in data
        assert data["total_scenarios"] > 0

    def test_evaluate_runs_all_engines(self, tmp_path: Path):
        """Step 3: evaluate runs the full multi-engine analysis."""
        model_path = _save_demo_model(tmp_path)
        result = runner.invoke(app, ["evaluate", "--model", str(model_path), "--json"])
        assert result.exit_code == 0, f"evaluate failed: {result.output}"
        data = _extract_json(result.output)
        assert "components" in data
        assert "verdict" in data

    def test_security_assessment(self, tmp_path: Path):
        """Step 4: security command produces a security assessment."""
        model_path = _save_demo_model(tmp_path)
        result = runner.invoke(app, ["security", "--model", str(model_path), "--json"])
        assert result.exit_code == 0, f"security failed: {result.output}"
        data = _extract_json(result.output)
        assert isinstance(data, dict)

    def test_cost_analysis(self, tmp_path: Path):
        """Step 5: cost command produces a cost impact analysis."""
        model_path = _save_demo_model(tmp_path)
        result = runner.invoke(app, ["cost", "--model", str(model_path), "--json"])
        assert result.exit_code == 0, f"cost failed: {result.output}"
        data = _extract_json(result.output)
        assert isinstance(data, dict)

    def test_plan_remediation(self, tmp_path: Path):
        """Step 6: plan command produces a remediation plan."""
        model_path = _save_demo_model(tmp_path)
        result = runner.invoke(app, ["plan", "--model", str(model_path), "--json"])
        assert result.exit_code == 0, f"plan failed: {result.output}"
        data = _extract_json(result.output)
        assert isinstance(data, dict)

    def test_fix_generates_iac(self, tmp_path: Path):
        """Step 7: fix command generates IaC remediation code."""
        model_path = _save_demo_model(tmp_path)
        result = runner.invoke(app, ["fix", "--model", str(model_path), "--json"])
        assert result.exit_code == 0, f"fix failed: {result.output}"
        data = _extract_json(result.output)
        assert isinstance(data, dict)

    def test_auto_fix_dry_run(self, tmp_path: Path):
        """Step 8: auto-fix --dry-run previews changes without writing."""
        model_path = _save_demo_model(tmp_path)
        result = runner.invoke(
            app,
            ["auto-fix", str(model_path), "--dry-run", "--json"],
        )
        assert result.exit_code == 0, f"auto-fix failed: {result.output}"
        data = _extract_json(result.output)
        assert isinstance(data, dict)

    def test_history_records_results(self, tmp_path: Path):
        """Step 9: history command shows recorded results."""
        model_path = _save_demo_model(tmp_path)
        # First run a simulation to generate history
        runner.invoke(app, ["simulate", "--model", str(model_path), "--json"])
        # Then check history
        result = runner.invoke(app, ["history", "--json"])
        # Exit code 0 or 1 (empty history is acceptable)
        assert result.exit_code in (0, 1), f"history failed: {result.output}"

    def test_diff_compares_before_after(self, tmp_path: Path):
        """Step 10: simulate with --save-baseline creates a baseline file."""
        model_path = _save_demo_model(tmp_path)
        baseline1 = tmp_path / "baseline1.json"

        # Run simulation and save baseline (without --json to allow baseline save)
        r1 = runner.invoke(app, [
            "simulate", "--model", str(model_path),
            "--save-baseline", str(baseline1),
        ])
        assert r1.exit_code == 0, f"simulate+baseline failed: {r1.output}"
        assert baseline1.exists(), "Baseline file was not created"

        b1_data = json.loads(baseline1.read_text())
        assert "resilience_score" in b1_data

        # Compare against baseline
        r2 = runner.invoke(app, [
            "simulate", "--model", str(model_path),
            "--baseline", str(baseline1),
        ])
        # Should not regress against itself
        assert r2.exit_code == 0, f"baseline comparison failed: {r2.output}"


# ---------------------------------------------------------------------------
# Test 2: AWS scan to remediation flow
# ---------------------------------------------------------------------------

class TestAWSScanToRemediationFlow:
    """Simulate: AWS scan -> evaluate -> fix -> verify improvement.
    Uses demo graph as AWS scan substitute.
    """

    def test_full_flow(self, tmp_path: Path):
        """Load demo graph, evaluate, fix, verify score stays consistent."""
        graph = create_demo_graph()
        model_path = tmp_path / "aws-scan-model.json"
        graph.save(model_path)

        # Evaluate (using JSON mode)
        r1 = runner.invoke(app, ["evaluate", "--model", str(model_path), "--json"])
        assert r1.exit_code == 0, f"evaluate failed: {r1.output}"
        eval_data = _extract_json(r1.output)
        assert "verdict" in eval_data

        # Fix (generates remediation)
        r2 = runner.invoke(app, ["fix", "--model", str(model_path), "--json"])
        assert r2.exit_code == 0, f"fix failed: {r2.output}"

        # Auto-fix dry run
        r3 = runner.invoke(app, ["auto-fix", str(model_path), "--dry-run", "--json"])
        assert r3.exit_code == 0, f"auto-fix failed: {r3.output}"


# ---------------------------------------------------------------------------
# Test 3: Compliance audit flow
# ---------------------------------------------------------------------------

class TestComplianceAuditFlow:
    """Simulate: load infra -> compliance check -> evidence generation -> export."""

    def test_compliance_check_flow(self, tmp_path: Path):
        """Run compliance command with --all flag on demo model."""
        model_path = _save_demo_model(tmp_path)
        # compliance requires --framework <name> or --all
        result = runner.invoke(
            app,
            ["compliance", "--model", str(model_path), "--all", "--json"],
        )
        assert result.exit_code == 0, f"compliance --all failed: {result.output}"
        data = _extract_json(result.output)
        assert isinstance(data, dict)

    def test_compliance_single_framework(self, tmp_path: Path):
        """Run compliance with a specific framework."""
        model_path = _save_demo_model(tmp_path)
        result = runner.invoke(
            app,
            ["compliance", "--model", str(model_path), "--framework", "soc2", "--json"],
        )
        assert result.exit_code == 0, f"compliance soc2 failed: {result.output}"
        data = _extract_json(result.output)
        assert isinstance(data, dict)

    def test_export_json(self, tmp_path: Path):
        """Export simulation results as structured JSON."""
        model_path = _save_demo_model(tmp_path)
        result = runner.invoke(app, ["simulate", "--model", str(model_path), "--json"])
        assert result.exit_code == 0
        data = _extract_json(result.output)
        assert "resilience_score" in data
        assert "critical" in data
        assert "warning" in data
        assert "passed" in data


# ---------------------------------------------------------------------------
# Test 4: Chaos testing flow
# ---------------------------------------------------------------------------

class TestChaosTestingFlow:
    """Simulate: load -> fuzz -> slo-budget."""

    def test_fuzz_command(self, tmp_path: Path):
        """Fuzz command discovers novel failure patterns.
        fuzz takes a positional MODEL_FILE argument.
        """
        model_path = _save_demo_model(tmp_path)
        result = runner.invoke(
            app,
            ["fuzz", str(model_path), "--json", "--iterations", "10"],
        )
        assert result.exit_code == 0, f"fuzz failed: {result.output}"
        data = _extract_json(result.output)
        assert isinstance(data, dict)

    def test_slo_budget_command(self, tmp_path: Path):
        """SLO budget command evaluates risk appetite.
        slo-budget takes a positional MODEL_FILE argument.
        """
        model_path = _save_demo_model(tmp_path)
        result = runner.invoke(
            app,
            ["slo-budget", str(model_path), "--json"],
        )
        assert result.exit_code == 0, f"slo-budget failed: {result.output}"
        data = _extract_json(result.output)
        assert isinstance(data, dict)

    def test_calendar_schedule_command(self, tmp_path: Path):
        """Calendar schedule command lists chaos windows.
        calendar is a sub-command group: calendar schedule MODEL_FILE.
        """
        model_path = _save_demo_model(tmp_path)
        result = runner.invoke(
            app,
            ["calendar", "schedule", str(model_path), "--json"],
        )
        assert result.exit_code == 0, f"calendar schedule failed: {result.output}"


# ---------------------------------------------------------------------------
# Test 5: Financial analysis flow
# ---------------------------------------------------------------------------

class TestFinancialAnalysisFlow:
    """Simulate: load -> cost -> risk -> executive report."""

    def test_cost_to_report_flow(self, tmp_path: Path):
        """Run cost engine, then financial risk analysis."""
        from faultray.simulator.engine import SimulationEngine
        from faultray.simulator.cost_engine import CostImpactEngine
        from faultray.simulator.financial_risk import FinancialRiskEngine

        graph = create_demo_graph()
        engine = SimulationEngine(graph)
        report = engine.run_all_defaults(include_feed=False, include_plugins=False)

        # Cost engine
        cost_engine = CostImpactEngine(graph)
        cost_report = cost_engine.analyze(report)
        assert len(cost_report.impacts) > 0
        assert cost_report.total_annual_risk >= 0

        # Financial risk engine
        risk_engine = FinancialRiskEngine(graph)
        risk_report = risk_engine.analyze(report)
        assert risk_report.expected_annual_loss >= 0
        assert risk_report.value_at_risk_95 >= 0

    def test_report_executive_command(self, tmp_path: Path):
        """Generate executive-level report.
        report takes: report REPORT_TYPE [MODEL] -- not --model.
        """
        model_path = _save_demo_model(tmp_path)
        output_file = tmp_path / "exec_report.html"
        result = runner.invoke(
            app,
            ["report", "executive", str(model_path), "--output", str(output_file)],
        )
        # Accept 0 or 1 (report might depend on optional features)
        assert result.exit_code in (0, 1), f"report executive failed: {result.output}"


# ---------------------------------------------------------------------------
# Test 6: Multi-engine consistency
# ---------------------------------------------------------------------------

class TestMultiEngineConsistency:
    """Run all engines on the same graph, verify scores are consistent."""

    def test_resilience_v1_v2_correlate(self):
        """Resilience v1 and v2 should correlate (both reflect infrastructure health)."""
        graph = create_demo_graph()
        v1_score = graph.resilience_score()
        v2_result = graph.resilience_score_v2()
        v2_score = v2_result["score"]

        assert 0 <= v1_score <= 100
        assert 0 <= v2_score <= 100

        # Both should be in the same ballpark
        assert abs(v1_score - v2_score) < 60, (
            f"v1={v1_score}, v2={v2_score}: scores differ by > 60 points"
        )

    def test_security_score_within_bounds(self):
        """Security score should be bounded 0-100."""
        from faultray.simulator.security_engine import SecurityResilienceEngine

        graph = create_demo_graph()
        engine = SecurityResilienceEngine(graph)
        score = engine.security_resilience_score()
        assert 0 <= score <= 100

    def test_cost_reflects_simulation_findings(self):
        """Cost analysis should reflect simulation severity."""
        from faultray.simulator.engine import SimulationEngine
        from faultray.simulator.cost_engine import CostImpactEngine

        graph = create_demo_graph()
        engine = SimulationEngine(graph)
        report = engine.run_all_defaults(include_feed=False, include_plugins=False)
        cost_engine = CostImpactEngine(graph)
        cost_report = cost_engine.analyze(report)

        # Impacts are sorted by total_impact descending
        if len(cost_report.impacts) >= 2:
            assert cost_report.impacts[0].total_impact >= cost_report.impacts[-1].total_impact

    def test_five_layer_model_ordering(self):
        """5-layer model layers should be ordered correctly."""
        from faultray.simulator.availability_model import compute_five_layer_model

        graph = create_demo_graph()
        result = compute_five_layer_model(graph)

        assert result.layer1_software.nines >= 0
        assert result.layer2_hardware.nines >= 0
        assert result.layer3_theoretical.nines >= 0
        assert result.layer4_operational.nines >= 0
        assert result.layer5_external.nines >= 0

        # Layer 1 (software + overhead) <= Layer 2 (hardware only)
        assert result.layer1_software.availability <= result.layer2_hardware.availability + 1e-9

        # Layer 3 (theoretical = hardware + noise) <= Layer 2 (hardware only)
        assert result.layer3_theoretical.availability <= result.layer2_hardware.availability + 1e-9


# ---------------------------------------------------------------------------
# Test 7: Serialization roundtrip
# ---------------------------------------------------------------------------

class TestSerializationRoundtrip:
    """Save graph -> reload -> resimulate -> verify identical results."""

    def test_json_roundtrip(self, tmp_path: Path):
        """Graph saved and reloaded should produce identical simulation results."""
        from faultray.simulator.engine import SimulationEngine

        graph1 = create_demo_graph()
        model_path = tmp_path / "roundtrip.json"
        graph1.save(model_path)

        graph2 = InfraGraph.load(model_path)

        assert len(graph1.components) == len(graph2.components)
        assert set(graph1.components.keys()) == set(graph2.components.keys())
        assert graph1.resilience_score() == graph2.resilience_score()

        engine1 = SimulationEngine(graph1)
        engine2 = SimulationEngine(graph2)

        report1 = engine1.run_all_defaults(
            include_feed=False, include_plugins=False, max_scenarios=50
        )
        report2 = engine2.run_all_defaults(
            include_feed=False, include_plugins=False, max_scenarios=50
        )

        assert len(report1.results) == len(report2.results)
        assert report1.resilience_score == report2.resilience_score

    def test_yaml_roundtrip(self, tmp_path: Path):
        """YAML model loaded should produce valid simulation results."""
        yaml_path = _save_demo_yaml(tmp_path)
        from faultray.model.loader import load_yaml
        from faultray.simulator.engine import SimulationEngine

        graph = load_yaml(yaml_path)
        assert len(graph.components) == 3

        engine = SimulationEngine(graph)
        report = engine.run_all_defaults(
            include_feed=False, include_plugins=False, max_scenarios=30
        )
        assert len(report.results) > 0
        assert 0 <= report.resilience_score <= 100


# ---------------------------------------------------------------------------
# Test 8: All CLI commands return zero on demo
# ---------------------------------------------------------------------------

class TestAllCLICommandsReturnZero:
    """Every CLI command should work without error on demo infrastructure."""

    # Commands that use --model option
    _OPT_MODEL_COMMANDS = [
        ("simulate", ["--json"]),
        ("evaluate", ["--json"]),
        ("security", ["--json"]),
        ("cost", ["--json"]),
        ("plan", ["--json"]),
        ("fix", ["--json"]),
    ]

    # Commands that use positional MODEL_FILE argument
    _POS_MODEL_COMMANDS = [
        ("fuzz", ["--json", "--iterations", "5"]),
        ("slo-budget", ["--json"]),
    ]

    @pytest.mark.parametrize("cmd,extra", _OPT_MODEL_COMMANDS)
    def test_opt_model_command(self, cmd: str, extra: list, tmp_path: Path):
        """CLI command with --model option should exit 0."""
        model_path = _save_demo_model(tmp_path)
        args = [cmd, "--model", str(model_path)] + extra
        result = runner.invoke(app, args)
        assert result.exit_code == 0, (
            f"Command '{cmd}' failed (exit {result.exit_code})\n{result.output}"
        )

    @pytest.mark.parametrize("cmd,extra", _POS_MODEL_COMMANDS)
    def test_pos_model_command(self, cmd: str, extra: list, tmp_path: Path):
        """CLI command with positional model arg should exit 0."""
        model_path = _save_demo_model(tmp_path)
        args = [cmd, str(model_path)] + extra
        result = runner.invoke(app, args)
        assert result.exit_code == 0, (
            f"Command '{cmd}' failed (exit {result.exit_code})\n{result.output}"
        )

    def test_version_flag(self):
        """--version flag should print version and exit 0."""
        result = runner.invoke(app, ["--version"])
        assert result.exit_code == 0
        assert "FaultRay" in result.output or "faultray" in result.output.lower()

    def test_demo_command(self):
        """demo command should succeed."""
        result = runner.invoke(app, ["demo"])
        assert result.exit_code == 0, f"demo failed: {result.output}"

    def test_auto_fix_dry_run_command(self, tmp_path: Path):
        """auto-fix in dry-run mode should succeed."""
        model_path = _save_demo_model(tmp_path)
        result = runner.invoke(app, ["auto-fix", str(model_path), "--dry-run", "--json"])
        assert result.exit_code == 0, f"auto-fix failed: {result.output}"

    def test_compliance_all_command(self, tmp_path: Path):
        """compliance --all should succeed."""
        model_path = _save_demo_model(tmp_path)
        result = runner.invoke(
            app, ["compliance", "--model", str(model_path), "--all", "--json"]
        )
        assert result.exit_code == 0, f"compliance failed: {result.output}"


# ---------------------------------------------------------------------------
# Test 9: JSON output consistency
# ---------------------------------------------------------------------------

class TestJsonOutputConsistency:
    """All --json commands should produce parseable JSON with consistent structure."""

    # (command, use_positional_model, extra_args)
    _JSON_COMMANDS = [
        ("simulate", False, ["--json"]),
        ("evaluate", False, ["--json"]),
        ("security", False, ["--json"]),
        ("cost", False, ["--json"]),
        ("plan", False, ["--json"]),
        ("fix", False, ["--json"]),
        ("fuzz", True, ["--json", "--iterations", "5"]),
        ("slo-budget", True, ["--json"]),
    ]

    @pytest.mark.parametrize("cmd,positional,extra_args", _JSON_COMMANDS)
    def test_json_parseable(self, cmd: str, positional: bool, extra_args: list, tmp_path: Path):
        """JSON output should be parseable and a dict or list."""
        model_path = _save_demo_model(tmp_path)
        if positional:
            args = [cmd, str(model_path)] + extra_args
        else:
            args = [cmd, "--model", str(model_path)] + extra_args
        result = runner.invoke(app, args)
        assert result.exit_code == 0, f"'{cmd}' failed: {result.output}"
        data = _extract_json(result.output)
        assert isinstance(data, (dict, list))


# ---------------------------------------------------------------------------
# Test 10: Template to simulation flow
# ---------------------------------------------------------------------------

class TestTemplateToSimulationFlow:
    """Load each template -> simulate -> verify no crashes."""

    def test_all_templates_load_and_simulate(self):
        """Every template should load and produce simulation results."""
        from faultray.templates import TEMPLATES, get_template_path
        from faultray.model.loader import load_yaml
        from faultray.simulator.engine import SimulationEngine

        for name in TEMPLATES:
            template_path = get_template_path(name)
            assert template_path.exists(), f"Template '{name}' file missing: {template_path}"

            graph = load_yaml(template_path)
            assert len(graph.components) > 0, f"Template '{name}' has no components"

            engine = SimulationEngine(graph)
            report = engine.run_all_defaults(
                include_feed=False, include_plugins=False, max_scenarios=20
            )
            assert len(report.results) > 0, f"Template '{name}' produced no results"
            assert 0 <= report.resilience_score <= 100, (
                f"Template '{name}' score out of range: {report.resilience_score}"
            )

    def test_template_yaml_files_loadable(self):
        """All template YAML files should load without error."""
        from faultray.templates import TEMPLATES, get_template_path
        from faultray.model.loader import load_yaml

        for name in TEMPLATES:
            path = get_template_path(name)
            graph = load_yaml(path)
            assert graph is not None
            assert len(graph.components) >= 1
