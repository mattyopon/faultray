"""Extended CLI tests targeting uncovered lines for 95%+ coverage.

Covers:
  - ops.py: ops_sim, whatif, capacity commands
  - main.py: _print_ops_results, _print_whatif_result, _print_multi_whatif_result,
             _print_ai_analysis, _load_graph_for_analysis
  - discovery.py: scan, load, show, tf_import, tf_plan
  - feeds.py: feed_update, feed_list, feed_sources, feed_clear
  - admin.py: demo --web, serve, report
  - simulate.py: simulate --dynamic, --plugins-dir, --pdf, --md, --slack-webhook, dynamic
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

import pytest
from click.exceptions import Exit as ClickExit
from typer.testing import CliRunner

from faultray.cli import app
from faultray.model.demo import create_demo_graph

runner = CliRunner()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_model_file(tmp_path: Path) -> Path:
    graph = create_demo_graph()
    model_path = tmp_path / "test-model.json"
    graph.save(model_path)
    return model_path


def _create_yaml_file(tmp_path: Path) -> Path:
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
    yaml_path = tmp_path / "infra.yaml"
    yaml_path.write_text(yaml_content, encoding="utf-8")
    return yaml_path


def _create_yaml_with_ops(tmp_path: Path) -> Path:
    """Create a YAML file with ops config section."""
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

dependencies:
  - source: web
    target: app
    type: requires
"""
    yaml_path = tmp_path / "infra-ops.yaml"
    yaml_path.write_text(yaml_content, encoding="utf-8")
    return yaml_path


# ---------------------------------------------------------------------------
# main.py: _print_ops_results
# ---------------------------------------------------------------------------

class TestPrintOpsResults:
    """Tests for _print_ops_results (main.py lines 139-264)."""

    def _make_sli_point(self, avail=99.99):
        return SimpleNamespace(availability_percent=avail)

    def _make_event(self, event_type="deploy", target="web", time_s=3600, desc="test event"):
        return SimpleNamespace(
            event_type=SimpleNamespace(value=event_type),
            target_component_id=target,
            time_seconds=time_s,
            description=desc,
        )

    def _make_error_budget(self, remaining_pct=75.0, exhausted=False, slo_name="Avail", comp_id="web"):
        return SimpleNamespace(
            slo=SimpleNamespace(name=slo_name, metric="availability"),
            component_id=comp_id,
            budget_total_minutes=43.2,
            budget_consumed_minutes=10.8,
            budget_remaining_minutes=32.4,
            budget_remaining_percent=remaining_pct,
            is_budget_exhausted=exhausted,
            burn_rate_1h=0.5,
            burn_rate_6h=0.8,
        )

    def _make_ops_result(
        self,
        avail=99.95,
        events=None,
        sli_timeline=None,
        error_budgets=None,
        summary="Test summary",
    ):
        from faultray.simulator.ops_engine import OpsScenario
        scenario = OpsScenario(
            id="test-scenario",
            name="Test Scenario",
            duration_days=7,
        )
        if sli_timeline is None:
            sli_timeline = [self._make_sli_point(avail)]
        if events is None:
            events = []
        if error_budgets is None:
            error_budgets = []
        return SimpleNamespace(
            scenario=scenario,
            sli_timeline=sli_timeline,
            min_availability=avail,
            events=events,
            error_budget_statuses=error_budgets,
            total_downtime_seconds=120.0,
            total_deploys=2,
            total_failures=1,
            total_degradation_events=0,
            peak_utilization=65.0,
            summary=summary,
        )

    def test_high_availability(self):
        from faultray.cli.main import _print_ops_results
        from rich.console import Console
        buf = StringIO()
        con = Console(file=buf, force_terminal=False, width=120)
        result = self._make_ops_result(avail=99.99)
        _print_ops_results(result, con)
        output = buf.getvalue()
        assert "Test Scenario" in output
        assert "99.99" in output

    def test_medium_availability(self):
        from faultray.cli.main import _print_ops_results
        from rich.console import Console
        buf = StringIO()
        con = Console(file=buf, force_terminal=False, width=120)
        result = self._make_ops_result(avail=99.5)
        _print_ops_results(result, con)
        output = buf.getvalue()
        assert "99.5" in output

    def test_low_availability(self):
        from faultray.cli.main import _print_ops_results
        from rich.console import Console
        buf = StringIO()
        con = Console(file=buf, force_terminal=False, width=120)
        result = self._make_ops_result(avail=98.0)
        _print_ops_results(result, con)
        output = buf.getvalue()
        assert "98.0" in output

    def test_with_events(self):
        from faultray.cli.main import _print_ops_results
        from rich.console import Console
        buf = StringIO()
        con = Console(file=buf, force_terminal=False, width=120)
        events = [
            self._make_event("deploy", "app", 3600),
            self._make_event("random_failure", "db", 7200),
            self._make_event("maintenance", "web", 14400),
            self._make_event("memory_leak_oom", "app", 86400),
            self._make_event("disk_full", "db", 86400 * 2),
            self._make_event("conn_pool_exhaustion", "app", 86400 * 3),
        ]
        result = self._make_ops_result(events=events)
        _print_ops_results(result, con)
        output = buf.getvalue()
        assert "Event Timeline" in output
        assert "Day" in output

    def test_with_error_budgets(self):
        from faultray.cli.main import _print_ops_results
        from rich.console import Console
        buf = StringIO()
        con = Console(file=buf, force_terminal=False, width=120)
        ebs = [
            self._make_error_budget(remaining_pct=75.0, exhausted=False),
            self._make_error_budget(remaining_pct=30.0, exhausted=False),
            self._make_error_budget(remaining_pct=10.0, exhausted=False),
            self._make_error_budget(remaining_pct=0.0, exhausted=True, slo_name="ErrorRate"),
        ]
        result = self._make_ops_result(error_budgets=ebs)
        _print_ops_results(result, con)
        output = buf.getvalue()
        assert "Error Budget" in output
        assert "EXHAUSTED" in output

    def test_empty_sli_timeline(self):
        from faultray.cli.main import _print_ops_results
        from rich.console import Console
        buf = StringIO()
        con = Console(file=buf, force_terminal=False, width=120)
        result = self._make_ops_result(sli_timeline=[])
        _print_ops_results(result, con)
        output = buf.getvalue()
        assert "Operational Simulation Report" in output

    def test_no_summary(self):
        from faultray.cli.main import _print_ops_results
        from rich.console import Console
        buf = StringIO()
        con = Console(file=buf, force_terminal=False, width=120)
        result = self._make_ops_result(summary="")
        _print_ops_results(result, con)
        # Should not crash

    def test_many_events_truncated(self):
        """More than 25 events should be truncated."""
        from faultray.cli.main import _print_ops_results
        from rich.console import Console
        buf = StringIO()
        con = Console(file=buf, force_terminal=False, width=120)
        events = [self._make_event("deploy", f"comp-{i}", i * 300) for i in range(30)]
        result = self._make_ops_result(events=events)
        _print_ops_results(result, con)
        output = buf.getvalue()
        assert "last 25 of 30" in output


# ---------------------------------------------------------------------------
# main.py: _print_whatif_result
# ---------------------------------------------------------------------------

class TestPrintWhatifResult:
    """Tests for _print_whatif_result (main.py lines 269-308)."""

    def _make_whatif_result(self, param="mttr_factor", breakpoint_val=None):
        return SimpleNamespace(
            parameter=param,
            values=[0.5, 1.0, 2.0],
            avg_availabilities=[99.99, 99.95, 99.5],
            min_availabilities=[99.9, 99.0, 98.0],
            total_failures=[0, 1, 5],
            total_downtimes=[0.0, 60.0, 300.0],
            slo_pass=[True, True, False],
            breakpoint_value=breakpoint_val,
        )

    def test_basic_whatif_output(self):
        from faultray.cli.main import _print_whatif_result
        from rich.console import Console
        buf = StringIO()
        con = Console(file=buf, force_terminal=False, width=120)
        result = self._make_whatif_result()
        _print_whatif_result(result, con)
        output = buf.getvalue()
        assert "Mttr Factor" in output
        assert "PASS" in output
        assert "FAIL" in output

    def test_with_breakpoint(self):
        from faultray.cli.main import _print_whatif_result
        from rich.console import Console
        buf = StringIO()
        con = Console(file=buf, force_terminal=False, width=120)
        result = self._make_whatif_result(breakpoint_val=1.5)
        _print_whatif_result(result, con)
        output = buf.getvalue()
        assert "Breakpoint" in output
        assert "1.50" in output

    def test_empty_values(self):
        from faultray.cli.main import _print_whatif_result
        from rich.console import Console
        buf = StringIO()
        con = Console(file=buf, force_terminal=False, width=120)
        result = SimpleNamespace(
            parameter="test_param",
            values=[],
            avg_availabilities=[],
            min_availabilities=[],
            total_failures=[],
            total_downtimes=[],
            slo_pass=[],
            breakpoint_value=None,
        )
        _print_whatif_result(result, con)
        # Should not crash


# ---------------------------------------------------------------------------
# main.py: _print_multi_whatif_result
# ---------------------------------------------------------------------------

class TestPrintMultiWhatifResult:
    """Tests for _print_multi_whatif_result (main.py lines 317-350)."""

    def test_basic_multi_result(self):
        from faultray.cli.main import _print_multi_whatif_result
        from rich.console import Console
        buf = StringIO()
        con = Console(file=buf, force_terminal=False, width=120)
        result = SimpleNamespace(
            parameters={"mttr_factor": 2.0, "traffic_factor": 3.0},
            avg_availability=99.5,
            min_availability=98.0,
            total_failures=5,
            total_downtime_seconds=300,
            slo_pass=False,
            summary="Analysis: worst case scenario\nDetails...",
        )
        _print_multi_whatif_result(result, con)
        output = buf.getvalue()
        assert "mttr_factor" in output
        assert "traffic_factor" in output
        assert "FAIL" in output

    def test_multi_result_with_pass(self):
        from faultray.cli.main import _print_multi_whatif_result
        from rich.console import Console
        buf = StringIO()
        con = Console(file=buf, force_terminal=False, width=120)
        result = SimpleNamespace(
            parameters={"mttr_factor": 1.0},
            avg_availability=99.99,
            min_availability=99.9,
            total_failures=0,
            total_downtime_seconds=0,
            slo_pass=True,
            summary="",
        )
        _print_multi_whatif_result(result, con)
        output = buf.getvalue()
        assert "PASS" in output

    def test_multi_result_no_analysis_prefix(self):
        from faultray.cli.main import _print_multi_whatif_result
        from rich.console import Console
        buf = StringIO()
        con = Console(file=buf, force_terminal=False, width=120)
        result = SimpleNamespace(
            parameters={"x": 1.0},
            avg_availability=99.0,
            min_availability=98.0,
            total_failures=0,
            total_downtime_seconds=0,
            slo_pass=True,
            summary="Some other summary",
        )
        _print_multi_whatif_result(result, con)
        output = buf.getvalue()
        assert "x" in output


# ---------------------------------------------------------------------------
# main.py: _print_ai_analysis
# ---------------------------------------------------------------------------

class TestPrintAiAnalysis:
    """Tests for _print_ai_analysis (main.py lines ~71-135)."""

    def test_full_ai_analysis(self):
        from faultray.cli.main import _print_ai_analysis
        from rich.console import Console
        buf = StringIO()
        con = Console(file=buf, force_terminal=False, width=200)

        rec = SimpleNamespace(
            severity="critical",
            category="reliability",
            title="Add redundancy",
            remediation="Deploy multi-AZ. " + "x" * 100,  # >80 chars to test truncation
            estimated_impact="High availability",
            effort="Medium",
        )
        rec2 = SimpleNamespace(
            severity="low",
            category="cost",
            title="Optimize instances",
            remediation="Right-size instances",
            estimated_impact="Cost savings",
            effort="Low",
        )
        ai_report = SimpleNamespace(
            summary="System needs redundancy improvements",
            top_risks=["Single point of failure at DB", "No autoscaling"],
            availability_assessment="Below target",
            estimated_current_nines=2.5,
            theoretical_max_nines=4.0,
            recommendations=[rec, rec2],
            upgrade_path="Step 1: Add replicas\nStep 2: Enable autoscaling",
        )
        _print_ai_analysis(ai_report, con)
        output = buf.getvalue()
        assert "AI Analysis Summary" in output
        assert "Top Risks" in output
        assert "Availability" in output
        assert "Recommendations" in output
        assert "Upgrade Path" in output

    def test_ai_analysis_no_risks_no_recs_no_upgrade(self):
        from faultray.cli.main import _print_ai_analysis
        from rich.console import Console
        buf = StringIO()
        con = Console(file=buf, force_terminal=False, width=120)
        ai_report = SimpleNamespace(
            summary="All good",
            top_risks=[],
            availability_assessment="Above target",
            estimated_current_nines=4.0,
            theoretical_max_nines=5.0,
            recommendations=[],
            upgrade_path="",
        )
        _print_ai_analysis(ai_report, con)
        output = buf.getvalue()
        assert "AI Analysis Summary" in output
        # Should not contain these sections when empty
        assert "Upgrade Path" not in output

    def test_ai_analysis_medium_and_high_severity(self):
        from faultray.cli.main import _print_ai_analysis
        from rich.console import Console
        buf = StringIO()
        con = Console(file=buf, force_terminal=False, width=200)
        recs = [
            SimpleNamespace(severity="high", category="sec", title="Fix XSS",
                            remediation="Sanitize inputs", estimated_impact="Security", effort="High"),
            SimpleNamespace(severity="medium", category="perf", title="Add cache",
                            remediation="Add Redis cache", estimated_impact="Performance", effort="Medium"),
        ]
        ai_report = SimpleNamespace(
            summary="Moderate issues",
            top_risks=["XSS vulnerability"],
            availability_assessment="OK",
            estimated_current_nines=3.0,
            theoretical_max_nines=4.5,
            recommendations=recs,
            upgrade_path="",
        )
        _print_ai_analysis(ai_report, con)
        output = buf.getvalue()
        assert "HIGH" in output
        assert "MEDIUM" in output


# ---------------------------------------------------------------------------
# main.py: _load_graph_for_analysis
# ---------------------------------------------------------------------------

class TestLoadGraphForAnalysis:
    """Tests for _load_graph_for_analysis (main.py lines 358-376)."""

    def test_load_from_yaml(self, tmp_path):
        from faultray.cli.main import _load_graph_for_analysis
        yaml_path = _create_yaml_file(tmp_path)
        graph = _load_graph_for_analysis(Path("nonexistent.json"), yaml_path)
        assert len(graph.components) == 3

    def test_load_yaml_not_found(self, tmp_path):
        from faultray.cli.main import _load_graph_for_analysis
        with pytest.raises(ClickExit):
            _load_graph_for_analysis(Path("x.json"), tmp_path / "missing.yaml")

    def test_load_from_model_json(self, tmp_path):
        from faultray.cli.main import _load_graph_for_analysis
        model_path = _create_model_file(tmp_path)
        graph = _load_graph_for_analysis(model_path, None)
        assert len(graph.components) > 0

    def test_load_model_not_found(self, tmp_path):
        from faultray.cli.main import _load_graph_for_analysis
        with pytest.raises(ClickExit):
            _load_graph_for_analysis(tmp_path / "missing.json", None)

    def test_load_from_yaml_model_path(self, tmp_path):
        """When model path ends with .yaml, load via load_yaml."""
        from faultray.cli.main import _load_graph_for_analysis
        yaml_path = _create_yaml_file(tmp_path)
        yaml_model = tmp_path / "model.yaml"
        yaml_path.rename(yaml_model)
        graph = _load_graph_for_analysis(yaml_model, None)
        assert len(graph.components) == 3

    def test_load_from_yml_model_path(self, tmp_path):
        """When model path ends with .yml, load via load_yaml."""
        from faultray.cli.main import _load_graph_for_analysis
        yaml_path = _create_yaml_file(tmp_path)
        yml_model = tmp_path / "model.yml"
        yaml_path.rename(yml_model)
        graph = _load_graph_for_analysis(yml_model, None)
        assert len(graph.components) == 3


# ---------------------------------------------------------------------------
# ops.py: ops_sim command
# ---------------------------------------------------------------------------

class TestOpsSim:
    """Tests for the ops-sim CLI command (ops.py lines 40-186)."""

    def test_ops_sim_with_yaml(self, tmp_path):
        yaml_path = _create_yaml_with_ops(tmp_path)
        result = runner.invoke(app, [
            "ops-sim", str(yaml_path),
            "--days", "1", "--step", "1hour",
        ])
        assert result.exit_code == 0
        assert "Operational Simulation Report" in result.output

    def test_ops_sim_with_model(self, tmp_path):
        model_path = _create_model_file(tmp_path)
        result = runner.invoke(app, [
            "ops-sim", "--model", str(model_path),
            "--days", "1", "--step", "1hour",
        ])
        assert result.exit_code == 0
        assert "Operational Simulation Report" in result.output

    def test_ops_sim_with_yaml_model(self, tmp_path):
        """Use --model with a YAML file (detected by extension)."""
        yaml_path = _create_yaml_with_ops(tmp_path)
        yaml_model = tmp_path / "model.yaml"
        yaml_path.rename(yaml_model)
        result = runner.invoke(app, [
            "ops-sim", "--model", str(yaml_model),
            "--days", "1", "--step", "1hour",
        ])
        assert result.exit_code == 0

    def test_ops_sim_defaults_mode(self, tmp_path):
        model_path = _create_model_file(tmp_path)
        result = runner.invoke(app, [
            "ops-sim", "--model", str(model_path),
            "--defaults",
        ])
        assert result.exit_code == 0

    def test_ops_sim_invalid_step(self, tmp_path):
        model_path = _create_model_file(tmp_path)
        result = runner.invoke(app, [
            "ops-sim", "--model", str(model_path),
            "--step", "invalid",
        ])
        assert result.exit_code != 0

    def test_ops_sim_invalid_days_too_low(self, tmp_path):
        model_path = _create_model_file(tmp_path)
        result = runner.invoke(app, [
            "ops-sim", "--model", str(model_path),
            "--days", "0",
        ])
        assert result.exit_code != 0

    def test_ops_sim_invalid_days_too_high(self, tmp_path):
        model_path = _create_model_file(tmp_path)
        result = runner.invoke(app, [
            "ops-sim", "--model", str(model_path),
            "--days", "31",
        ])
        assert result.exit_code != 0

    def test_ops_sim_invalid_diurnal_peak(self, tmp_path):
        model_path = _create_model_file(tmp_path)
        result = runner.invoke(app, [
            "ops-sim", "--model", str(model_path),
            "--diurnal-peak", "0.5",
        ])
        assert result.exit_code != 0

    def test_ops_sim_invalid_deploy_hour(self, tmp_path):
        model_path = _create_model_file(tmp_path)
        result = runner.invoke(app, [
            "ops-sim", "--model", str(model_path),
            "--deploy-hour", "25",
        ])
        assert result.exit_code != 0

    def test_ops_sim_missing_model(self, tmp_path):
        result = runner.invoke(app, [
            "ops-sim", "--model", str(tmp_path / "nonexistent.json"),
        ])
        assert result.exit_code != 0

    def test_ops_sim_missing_yaml(self, tmp_path):
        result = runner.invoke(app, [
            "ops-sim", "--yaml", str(tmp_path / "nonexistent.yaml"),
        ])
        assert result.exit_code != 0

    def test_ops_sim_with_growth(self, tmp_path):
        model_path = _create_model_file(tmp_path)
        result = runner.invoke(app, [
            "ops-sim", "--model", str(model_path),
            "--days", "1", "--step", "1hour",
            "--growth", "0.1",
        ])
        assert result.exit_code == 0

    def test_ops_sim_with_deploy_days(self, tmp_path):
        model_path = _create_model_file(tmp_path)
        result = runner.invoke(app, [
            "ops-sim", "--model", str(model_path),
            "--days", "1", "--step", "1hour",
            "--deploy-days", "mon,wed,fri",
        ])
        assert result.exit_code == 0

    def test_ops_sim_with_no_flags(self, tmp_path):
        model_path = _create_model_file(tmp_path)
        result = runner.invoke(app, [
            "ops-sim", "--model", str(model_path),
            "--days", "1", "--step", "1hour",
            "--no-random-failures",
            "--no-degradation",
            "--no-maintenance",
        ])
        assert result.exit_code == 0

    def test_ops_sim_with_html(self, tmp_path):
        model_path = _create_model_file(tmp_path)
        html_path = tmp_path / "ops-report.html"
        result = runner.invoke(app, [
            "ops-sim", "--model", str(model_path),
            "--days", "1", "--step", "1hour",
            "--html", str(html_path),
        ])
        assert result.exit_code == 0
        assert "HTML export" in result.output

    def test_ops_sim_yaml_load_error(self, tmp_path):
        """YAML file exists but has invalid model content (ValueError)."""
        bad_yaml = tmp_path / "bad.yaml"
        bad_yaml.write_text("components:\n  - id: x\n    type: invalid_type\n", encoding="utf-8")
        result = runner.invoke(app, [
            "ops-sim", str(bad_yaml),
        ])
        assert result.exit_code != 0

    def test_ops_sim_yaml_model_load_error(self, tmp_path):
        """Model is a YAML file that fails to load (ValueError)."""
        bad_yaml = tmp_path / "bad.yaml"
        bad_yaml.write_text("components:\n  - id: x\n    type: invalid_type\n", encoding="utf-8")
        result = runner.invoke(app, [
            "ops-sim", "--model", str(bad_yaml),
        ])
        assert result.exit_code != 0

    def test_ops_sim_defaults_with_step_override(self, tmp_path):
        model_path = _create_model_file(tmp_path)
        result = runner.invoke(app, [
            "ops-sim", "--model", str(model_path),
            "--defaults", "--step", "1min",
        ])
        assert result.exit_code == 0

    def test_ops_sim_negative_deploy_hour(self, tmp_path):
        model_path = _create_model_file(tmp_path)
        result = runner.invoke(app, [
            "ops-sim", "--model", str(model_path),
            "--deploy-hour", "-1",
        ])
        assert result.exit_code != 0

    def test_ops_sim_no_app_server_components(self, tmp_path):
        """When no app_server/web_server components, fall back to first 2 component IDs."""
        # Create a YAML with only database and cache types
        yaml_content = """\
components:
  - id: db1
    name: db-primary
    type: database
    host: db01
    port: 5432
    replicas: 1
    metrics:
      cpu_percent: 40
      memory_percent: 60
    capacity:
      max_connections: 100

  - id: cache1
    name: redis-cache
    type: cache
    host: cache01
    port: 6379
    replicas: 1
    metrics:
      cpu_percent: 20
      memory_percent: 30
    capacity:
      max_connections: 500
"""
        yaml_path = tmp_path / "no-app.yaml"
        yaml_path.write_text(yaml_content, encoding="utf-8")
        result = runner.invoke(app, [
            "ops-sim", str(yaml_path),
            "--days", "1", "--step", "1hour",
        ])
        assert result.exit_code == 0


# ---------------------------------------------------------------------------
# ops.py: whatif command
# ---------------------------------------------------------------------------

class TestWhatif:
    """Tests for the whatif CLI command (ops.py lines 204-264)."""

    def test_whatif_defaults(self, tmp_path):
        yaml_path = _create_yaml_file(tmp_path)
        result = runner.invoke(app, [
            "whatif", str(yaml_path), "--defaults",
        ])
        assert result.exit_code == 0
        assert "What-if" in result.output

    def test_whatif_parameter_and_values(self, tmp_path):
        yaml_path = _create_yaml_file(tmp_path)
        result = runner.invoke(app, [
            "whatif", str(yaml_path),
            "--parameter", "mttr_factor",
            "--values", "0.5,1.0,2.0",
        ])
        assert result.exit_code == 0
        assert "Mttr Factor" in result.output

    def test_whatif_no_args(self, tmp_path):
        yaml_path = _create_yaml_file(tmp_path)
        result = runner.invoke(app, [
            "whatif", str(yaml_path),
        ])
        assert result.exit_code != 0

    def test_whatif_multi_defaults(self, tmp_path):
        yaml_path = _create_yaml_file(tmp_path)
        result = runner.invoke(app, [
            "whatif", str(yaml_path),
            "--multi", "defaults",
        ])
        assert result.exit_code == 0
        assert "Multi What-if" in result.output

    def test_whatif_multi_custom(self, tmp_path):
        yaml_path = _create_yaml_file(tmp_path)
        result = runner.invoke(app, [
            "whatif", str(yaml_path),
            "--multi", "mttr_factor=2.0,traffic_factor=3.0",
        ])
        assert result.exit_code == 0

    def test_whatif_multi_invalid_format(self, tmp_path):
        yaml_path = _create_yaml_file(tmp_path)
        result = runner.invoke(app, [
            "whatif", str(yaml_path),
            "--multi", "bad_format_no_equals",
        ])
        assert result.exit_code != 0

    def test_whatif_with_model(self, tmp_path):
        model_path = _create_model_file(tmp_path)
        result = runner.invoke(app, [
            "whatif", "--model", str(model_path), "--defaults",
        ])
        assert result.exit_code == 0

    def test_whatif_import_error(self, tmp_path):
        """When WhatIfEngine is not importable, should show error."""
        yaml_path = _create_yaml_file(tmp_path)
        import builtins
        real_import = builtins.__import__
        def mock_import(name, *args, **kwargs):
            if name == "faultray.simulator.whatif_engine":
                raise ImportError("no module")
            return real_import(name, *args, **kwargs)
        with patch("builtins.__import__", side_effect=mock_import):
            result = runner.invoke(app, [
                "whatif", str(yaml_path), "--defaults",
            ])
            assert result.exit_code != 0


# ---------------------------------------------------------------------------
# ops.py: capacity command
# ---------------------------------------------------------------------------

class TestCapacity:
    """Tests for the capacity CLI command (ops.py lines 277-372)."""

    def test_capacity_with_yaml(self, tmp_path):
        yaml_path = _create_yaml_file(tmp_path)
        result = runner.invoke(app, [
            "capacity", str(yaml_path),
        ])
        assert result.exit_code == 0
        assert "Component Forecasts" in result.output or "Error Budget" in result.output

    def test_capacity_with_model(self, tmp_path):
        model_path = _create_model_file(tmp_path)
        result = runner.invoke(app, [
            "capacity", "--model", str(model_path),
        ])
        assert result.exit_code == 0
        assert "Error Budget" in result.output

    def test_capacity_custom_growth_and_slo(self, tmp_path):
        yaml_path = _create_yaml_file(tmp_path)
        result = runner.invoke(app, [
            "capacity", str(yaml_path),
            "--growth", "0.20",
            "--slo", "99.0",
        ])
        assert result.exit_code == 0

    def test_capacity_with_simulate(self, tmp_path):
        yaml_path = _create_yaml_file(tmp_path)
        result = runner.invoke(app, [
            "capacity", str(yaml_path),
            "--simulate",
        ])
        assert result.exit_code == 0
        assert "Error Budget" in result.output

    def test_capacity_missing_model(self, tmp_path):
        result = runner.invoke(app, [
            "capacity", "--model", str(tmp_path / "nonexistent.json"),
        ])
        assert result.exit_code != 0

    def test_capacity_import_error(self, tmp_path):
        """When CapacityPlanningEngine is not importable, should show error."""
        yaml_path = _create_yaml_file(tmp_path)
        import builtins
        real_import = builtins.__import__
        def mock_import(name, *args, **kwargs):
            if name == "faultray.simulator.capacity_engine":
                raise ImportError("no module")
            return real_import(name, *args, **kwargs)
        with patch("builtins.__import__", side_effect=mock_import):
            result = runner.invoke(app, [
                "capacity", str(yaml_path),
            ])
            assert result.exit_code != 0


# ---------------------------------------------------------------------------
# discovery.py: scan command
# ---------------------------------------------------------------------------

class TestScan:
    """Tests for the scan CLI command (discovery.py lines 31-44)."""

    def test_scan_local(self, tmp_path):
        output_path = tmp_path / "scanned.json"
        result = runner.invoke(app, [
            "scan", "--output", str(output_path),
        ])
        assert result.exit_code == 0
        assert output_path.exists()
        assert "Model saved" in result.output

    def test_scan_with_hostname(self, tmp_path):
        output_path = tmp_path / "scanned.json"
        result = runner.invoke(app, [
            "scan", "--output", str(output_path),
            "--hostname", "test-host",
        ])
        assert result.exit_code == 0

    def test_scan_with_prometheus(self, tmp_path):
        output_path = tmp_path / "scanned.json"
        graph = create_demo_graph()
        # Patch at the source modules since they're imported lazily inside the function
        with patch("faultray.discovery.prometheus.PrometheusClient") as MockClient:
            mock_instance = MagicMock()
            MockClient.return_value = mock_instance
            # asyncio.run is called in the CLI function, patch it there
            with patch("asyncio.run", return_value=graph):
                result = runner.invoke(app, [
                    "scan", "--output", str(output_path),
                    "--prometheus-url", "http://localhost:9090",
                ])
                assert result.exit_code == 0


# ---------------------------------------------------------------------------
# discovery.py: load command
# ---------------------------------------------------------------------------

class TestLoadYaml:
    """Tests for the load CLI command (discovery.py lines 62-64)."""

    def test_load_valid_yaml(self, tmp_path):
        yaml_path = _create_yaml_file(tmp_path)
        output = tmp_path / "output.json"
        result = runner.invoke(app, [
            "load", str(yaml_path), "--output", str(output),
        ])
        assert result.exit_code == 0
        assert output.exists()

    def test_load_invalid_yaml(self, tmp_path):
        bad_yaml = tmp_path / "bad.yaml"
        bad_yaml.write_text("components:\n  - id: x\n    type: invalid_type\n", encoding="utf-8")
        result = runner.invoke(app, [
            "load", str(bad_yaml),
        ])
        assert result.exit_code != 0


# ---------------------------------------------------------------------------
# discovery.py: show command (utilization colors)
# ---------------------------------------------------------------------------

class TestShowExtended:
    """Tests for show command covering utilization color branches (discovery.py line 92)."""

    def test_show_utilization_colors(self, tmp_path):
        """Covers the yellow branch (util > 60) and green branch."""
        from faultray.model.graph import InfraGraph
        from faultray.model.components import Component, ComponentType, ResourceMetrics, Capacity

        graph = InfraGraph()
        # High utilization (red, >80)
        graph.add_component(Component(
            id="high-util", name="high-util", type=ComponentType.APP_SERVER,
            host="h1", port=80, replicas=1,
            metrics=ResourceMetrics(cpu_percent=90, memory_percent=90),
            capacity=Capacity(max_connections=100),
        ))
        # Medium utilization (yellow, >60)
        graph.add_component(Component(
            id="mid-util", name="mid-util", type=ComponentType.APP_SERVER,
            host="h2", port=80, replicas=1,
            metrics=ResourceMetrics(cpu_percent=70, memory_percent=70),
            capacity=Capacity(max_connections=100),
        ))
        # Low utilization (green, <=60)
        graph.add_component(Component(
            id="low-util", name="low-util", type=ComponentType.APP_SERVER,
            host="h3", port=80, replicas=1,
            metrics=ResourceMetrics(cpu_percent=30, memory_percent=30),
            capacity=Capacity(max_connections=100),
        ))
        from faultray.model.graph import Dependency
        graph.add_dependency(Dependency(source_id="high-util", target_id="mid-util"))

        model_path = tmp_path / "model.json"
        graph.save(model_path)

        result = runner.invoke(app, ["show", "--model", str(model_path)])
        assert result.exit_code == 0
        assert "high-util" in result.output
        assert "mid-util" in result.output
        assert "low-util" in result.output


# ---------------------------------------------------------------------------
# discovery.py: tf_import command
# ---------------------------------------------------------------------------

class TestTfImport:
    """Tests for tf-import CLI command (discovery.py lines 112-136)."""

    def test_tf_import_state_file(self, tmp_path):
        graph = create_demo_graph()
        output = tmp_path / "tf-model.json"
        state_file = tmp_path / "terraform.tfstate"
        state_file.write_text("{}", encoding="utf-8")
        with patch("faultray.discovery.terraform.load_tf_state_file", return_value=graph):
            result = runner.invoke(app, [
                "tf-import", "--state", str(state_file), "--output", str(output),
            ])
            assert result.exit_code == 0
            assert "Model saved" in result.output

    def test_tf_import_dir(self, tmp_path):
        graph = create_demo_graph()
        output = tmp_path / "tf-model.json"
        with patch("faultray.discovery.terraform.load_tf_state_cmd", return_value=graph):
            result = runner.invoke(app, [
                "tf-import", "--dir", str(tmp_path), "--output", str(output),
            ])
            assert result.exit_code == 0

    def test_tf_import_dir_error_falls_back_to_hcl(self, tmp_path):
        """When terraform show fails with --dir, falls back to HCL parsing."""
        with patch("faultray.discovery.terraform.load_tf_state_cmd", side_effect=RuntimeError("terraform not found")):
            result = runner.invoke(app, [
                "tf-import", "--dir", str(tmp_path),
            ])
            assert result.exit_code == 0
            assert "falling back to HCL" in result.output

    def test_tf_import_no_args(self, tmp_path):
        """When no --state or --dir, runs in current directory."""
        graph = create_demo_graph()
        with patch("faultray.discovery.terraform.load_tf_state_cmd", return_value=graph):
            output = tmp_path / "out.json"
            result = runner.invoke(app, [
                "tf-import", "--output", str(output),
            ])
            assert result.exit_code == 0

    def test_tf_import_no_args_error(self, tmp_path):
        with patch("faultray.discovery.terraform.load_tf_state_cmd", side_effect=RuntimeError("no state")):
            result = runner.invoke(app, [
                "tf-import",
            ])
            assert result.exit_code != 0


# ---------------------------------------------------------------------------
# discovery.py: tf_plan command
# ---------------------------------------------------------------------------

class TestTfPlan:
    """Tests for tf-plan CLI command (discovery.py lines 153-212)."""

    def test_tf_plan_with_changes(self, tmp_path):
        graph = create_demo_graph()
        plan_result = {
            "changes": [
                {
                    "address": "aws_instance.web",
                    "actions": ["update"],
                    "risk_level": 3,
                    "changed_attributes": [
                        {"attribute": "instance_type", "before": "t3.micro", "after": "t3.small"},
                    ],
                },
                {
                    "address": "aws_instance.db",
                    "actions": ["delete", "create"],
                    "risk_level": 9,
                    "changed_attributes": [
                        {"attribute": "engine", "before": "postgres", "after": "mysql"},
                        {"attribute": "size", "before": "small", "after": "large"},
                        {"attribute": "storage", "before": "100", "after": "200"},
                        {"attribute": "iops", "before": "3000", "after": "6000"},
                    ],
                },
                {
                    "address": "aws_instance.cache",
                    "actions": ["update"],
                    "risk_level": 5,
                    "changed_attributes": [
                        {"attribute": "size", "before": "small", "after": "medium"},
                    ],
                },
            ],
            "after": graph,
        }
        plan_file = tmp_path / "plan.out"
        plan_file.write_text("plan", encoding="utf-8")

        with patch("faultray.discovery.terraform.load_tf_plan_cmd", return_value=plan_result):
            result = runner.invoke(app, [
                "tf-plan", str(plan_file),
            ])
            assert result.exit_code == 0
            assert "Terraform Changes" in result.output

    def test_tf_plan_no_changes(self, tmp_path):
        graph = create_demo_graph()
        plan_result = {"changes": [], "after": graph}
        plan_file = tmp_path / "plan.out"
        plan_file.write_text("plan", encoding="utf-8")

        with patch("faultray.discovery.terraform.load_tf_plan_cmd", return_value=plan_result):
            result = runner.invoke(app, [
                "tf-plan", str(plan_file),
            ])
            assert result.exit_code == 0
            assert "No changes" in result.output

    def test_tf_plan_error(self, tmp_path):
        plan_file = tmp_path / "plan.out"
        plan_file.write_text("plan", encoding="utf-8")

        with patch("faultray.discovery.terraform.load_tf_plan_cmd", side_effect=RuntimeError("plan error")):
            result = runner.invoke(app, [
                "tf-plan", str(plan_file),
            ])
            assert result.exit_code != 0

    def test_tf_plan_with_html(self, tmp_path):
        graph = create_demo_graph()
        plan_result = {
            "changes": [
                {
                    "address": "aws_instance.web",
                    "actions": ["update"],
                    "risk_level": 3,
                    "changed_attributes": [
                        {"attribute": "type", "before": "t3.micro", "after": "t3.small"},
                    ],
                },
            ],
            "after": graph,
        }
        plan_file = tmp_path / "plan.out"
        plan_file.write_text("plan", encoding="utf-8")
        html_path = tmp_path / "tf-report.html"

        with patch("faultray.discovery.terraform.load_tf_plan_cmd", return_value=plan_result):
            with patch("faultray.reporter.html_report.save_html_report"):
                result = runner.invoke(app, [
                    "tf-plan", str(plan_file), "--html", str(html_path),
                ])
                assert result.exit_code == 0


# ---------------------------------------------------------------------------
# feeds.py: feed_update command
# ---------------------------------------------------------------------------

class TestFeedUpdate:
    """Tests for feed-update CLI command (feeds.py lines 24-106)."""

    def _mock_article(self, title="Test CVE Article", source="CISA"):
        return SimpleNamespace(
            title=title,
            link="https://example.com/article",
            summary="A critical vulnerability was found",
            published="2024-01-01",
            source_name=source,
            tags=["cve"],
        )

    def _mock_incident(self, pattern_name="DDoS Attack", confidence=0.8, keywords=None):
        return SimpleNamespace(
            article=self._mock_article(),
            pattern=SimpleNamespace(
                id="ddos-pattern",
                name=pattern_name,
            ),
            matched_keywords=keywords or ["ddos", "attack", "flood"],
            confidence=confidence,
        )

    def test_feed_update_with_articles_and_incidents(self, tmp_path):
        model_path = _create_model_file(tmp_path)
        articles = [self._mock_article()]
        incidents = [
            self._mock_incident(confidence=0.8),
            self._mock_incident(confidence=0.5, pattern_name="SQL Injection"),
            self._mock_incident(confidence=0.3, pattern_name="Minor Issue"),
        ]
        mock_scenario = SimpleNamespace(id="feed-scenario-1", name="test")

        with patch("faultray.feeds.sources.get_enabled_sources", return_value=[MagicMock()]):
            with patch("faultray.feeds.fetcher.fetch_all_feeds", new_callable=AsyncMock, return_value=articles):
                with patch("asyncio.run", return_value=articles) as mock_arun:
                    with patch("faultray.feeds.analyzer.analyze_articles", return_value=incidents):
                        with patch("faultray.feeds.analyzer.incidents_to_scenarios", return_value=[mock_scenario]):
                            with patch("faultray.feeds.store.save_feed_scenarios", return_value=Path("/tmp/store.json")):
                                result = runner.invoke(app, [
                                    "feed-update", "--model", str(model_path),
                                ])
                                assert result.exit_code == 0
                                assert "Generated" in result.output

    def test_feed_update_no_articles(self, tmp_path):
        with patch("faultray.feeds.sources.get_enabled_sources", return_value=[MagicMock()]):
            with patch("asyncio.run", return_value=[]):
                result = runner.invoke(app, ["feed-update"])
                assert result.exit_code == 0
                assert "No articles" in result.output

    def test_feed_update_no_incidents(self, tmp_path):
        articles = [self._mock_article()]
        with patch("faultray.feeds.sources.get_enabled_sources", return_value=[MagicMock()]):
            with patch("asyncio.run", return_value=articles):
                with patch("faultray.feeds.analyzer.analyze_articles", return_value=[]):
                    result = runner.invoke(app, ["feed-update"])
                    assert result.exit_code == 0
                    assert "No new incident" in result.output

    def test_feed_update_no_model(self, tmp_path):
        """When model file doesn't exist, generates generic scenarios."""
        articles = [self._mock_article()]
        incidents = [self._mock_incident()]
        mock_scenario = SimpleNamespace(id="feed-scenario-1", name="test")

        with patch("faultray.feeds.sources.get_enabled_sources", return_value=[MagicMock()]):
            with patch("asyncio.run", return_value=articles):
                with patch("faultray.feeds.analyzer.analyze_articles", return_value=incidents):
                    with patch("faultray.feeds.analyzer.incidents_to_scenarios", return_value=[mock_scenario]):
                        with patch("faultray.feeds.store.save_feed_scenarios", return_value=Path("/tmp/store.json")):
                            result = runner.invoke(app, [
                                "feed-update", "--model", str(tmp_path / "nonexistent.json"),
                            ])
                            assert result.exit_code == 0
                            assert "generic" in result.output.lower() or "Generated" in result.output


# ---------------------------------------------------------------------------
# feeds.py: feed_list command
# ---------------------------------------------------------------------------

class TestFeedListExtended:
    """Tests for feed-list CLI command (feeds.py lines 118-119, 167-189)."""

    def test_feed_list_with_data(self):
        mock_stats = {
            "last_updated": "2024-01-01T00:00:00",
            "scenario_count": 5,
            "article_count": 10,
            "store_path": "/tmp/store.json",
        }
        mock_raw = {
            "scenarios": [
                {"id": "s1-long-id-here-1234", "name": "DDoS Scenario", "faults": [{"type": "traffic"}], "traffic_multiplier": 5.0},
                {"id": "s2-long-id-here-5678", "name": "Normal Scenario", "faults": [], "traffic_multiplier": 1.0},
            ],
            "articles": [
                {"title": f"Article {i}", "source": "CISA", "confidence": 0.8}
                for i in range(15)
            ],
        }
        with patch("faultray.feeds.store.get_store_stats", return_value=mock_stats):
            with patch("faultray.feeds.store.load_store_raw", return_value=mock_raw):
                result = runner.invoke(app, ["feed-list"])
                assert result.exit_code == 0
                assert "Feed Scenario Store" in result.output
                assert "DDoS Scenario" in result.output

    def test_feed_list_no_data(self):
        mock_stats = {
            "last_updated": None,
            "scenario_count": 0,
            "article_count": 0,
            "store_path": "/tmp/store.json",
        }
        with patch("faultray.feeds.store.get_store_stats", return_value=mock_stats):
            with patch("faultray.feeds.store.load_store_raw", return_value={}):
                result = runner.invoke(app, ["feed-list"])
                assert result.exit_code == 0
                assert "No feed data" in result.output


# ---------------------------------------------------------------------------
# feeds.py: feed_sources command
# ---------------------------------------------------------------------------

class TestFeedSources:
    """Tests for feed-sources CLI command (feeds.py lines 167-189)."""

    def test_feed_sources(self):
        result = runner.invoke(app, ["feed-sources"])
        assert result.exit_code == 0
        assert "Security News Feed Sources" in result.output
        assert "sources configured" in result.output


# ---------------------------------------------------------------------------
# feeds.py: feed_clear command
# ---------------------------------------------------------------------------

class TestFeedClear:
    """Tests for feed-clear CLI command (feeds.py lines 195-203)."""

    def test_feed_clear_with_data(self):
        mock_stats = {
            "last_updated": "2024-01-01T00:00:00",
            "scenario_count": 5,
            "article_count": 10,
            "store_path": "/tmp/store.json",
        }
        with patch("faultray.feeds.store.get_store_stats", return_value=mock_stats):
            with patch("faultray.feeds.store.clear_store") as mock_clear:
                result = runner.invoke(app, ["feed-clear"])
                assert result.exit_code == 0
                assert "Cleared" in result.output
                mock_clear.assert_called_once()

    def test_feed_clear_already_empty(self):
        mock_stats = {
            "last_updated": None,
            "scenario_count": 0,
            "article_count": 0,
            "store_path": "/tmp/store.json",
        }
        with patch("faultray.feeds.store.get_store_stats", return_value=mock_stats):
            result = runner.invoke(app, ["feed-clear"])
            assert result.exit_code == 0
            assert "already empty" in result.output


# ---------------------------------------------------------------------------
# admin.py: demo --web, serve, report
# ---------------------------------------------------------------------------

class TestAdminExtended:
    """Tests for admin CLI commands (admin.py lines 45-51, 63-86)."""

    def test_demo_with_web(self, tmp_path):
        """Test demo --web flag - mock uvicorn to avoid starting a server."""
        with patch("uvicorn.run") as mock_run:
            with patch("faultray.api.server.set_graph") as mock_set:
                result = runner.invoke(app, ["demo", "--web", "--port", "9999"])
                assert result.exit_code == 0
                mock_set.assert_called_once()
                mock_run.assert_called_once()

    def test_serve_with_model(self, tmp_path):
        model_path = _create_model_file(tmp_path)
        with patch("uvicorn.run") as mock_run:
            with patch("faultray.api.server.set_graph"):
                result = runner.invoke(app, [
                    "serve", "--model", str(model_path),
                    "--port", "9999",
                ])
                assert result.exit_code == 0
                mock_run.assert_called_once()

    def test_serve_no_model(self, tmp_path):
        with patch("uvicorn.run") as mock_run:
            result = runner.invoke(app, [
                "serve", "--model", str(tmp_path / "nonexistent.json"),
                "--port", "9999",
            ])
            assert result.exit_code == 0
            assert "No model file found" in result.output

    def test_serve_with_prometheus(self, tmp_path):
        model_path = _create_model_file(tmp_path)
        with patch("uvicorn.run"):
            with patch("faultray.api.server.set_graph"):
                with patch.dict("os.environ", {}, clear=False):
                    result = runner.invoke(app, [
                        "serve", "--model", str(model_path),
                        "--port", "9999",
                        "--prometheus-url", "http://prom:9090",
                        "--prometheus-interval", "30",
                    ])
                    assert result.exit_code == 0
                    assert "Prometheus monitoring enabled" in result.output

    def test_report_generates_html(self, tmp_path):
        model_path = _create_model_file(tmp_path)
        output_html = tmp_path / "report.html"
        result = runner.invoke(app, [
            "report", "executive", str(model_path), "--output", str(output_html),
        ])
        assert result.exit_code == 0
        assert output_html.exists()

    def test_report_missing_model(self, tmp_path):
        result = runner.invoke(app, [
            "report", "--model", str(tmp_path / "missing.json"),
        ])
        assert result.exit_code != 0


# ---------------------------------------------------------------------------
# simulate.py: simulate with plugins, pdf, md, webhooks, dynamic
# ---------------------------------------------------------------------------

class TestSimulateExtended:
    """Tests for simulate CLI command (simulate.py lines 41-44, 50-58, 95-122, 155-158)."""

    def test_simulate_with_plugins_dir(self, tmp_path):
        model_path = _create_model_file(tmp_path)
        plugins_dir = tmp_path / "plugins"
        plugins_dir.mkdir()
        with patch("faultray.plugins.registry.PluginRegistry.load_plugins_from_dir"):
            result = runner.invoke(app, [
                "simulate", "--model", str(model_path),
                "--plugins-dir", str(plugins_dir),
            ])
            assert result.exit_code == 0

    def test_simulate_dynamic_flag(self, tmp_path):
        model_path = _create_model_file(tmp_path)
        result = runner.invoke(app, [
            "simulate", "--model", str(model_path), "--dynamic",
        ])
        assert result.exit_code == 0
        assert "Dynamic Simulation" in result.output

    def test_simulate_with_pdf(self, tmp_path):
        model_path = _create_model_file(tmp_path)
        pdf_path = tmp_path / "report.html"
        with patch("faultray.reporter.pdf_report.save_pdf_ready_html") as mock_pdf:
            result = runner.invoke(app, [
                "simulate", "--model", str(model_path),
                "--pdf", str(pdf_path),
            ])
            assert result.exit_code == 0
            mock_pdf.assert_called_once()

    def test_simulate_with_md(self, tmp_path):
        model_path = _create_model_file(tmp_path)
        md_path = tmp_path / "report.md"
        with patch("faultray.reporter.pdf_report.export_markdown") as mock_md:
            result = runner.invoke(app, [
                "simulate", "--model", str(model_path),
                "--md", str(md_path),
            ])
            assert result.exit_code == 0
            mock_md.assert_called_once()

    def test_simulate_with_slack_webhook(self, tmp_path):
        model_path = _create_model_file(tmp_path)
        with patch("faultray.integrations.webhooks.send_slack_notification", new_callable=AsyncMock, return_value=True):
            with patch("faultray.api.server._report_to_dict", return_value={}):
                result = runner.invoke(app, [
                    "simulate", "--model", str(model_path),
                    "--slack-webhook", "https://hooks.slack.com/test",
                ])
                assert result.exit_code == 0

    def test_simulate_with_pagerduty_key(self, tmp_path):
        model_path = _create_model_file(tmp_path)
        with patch("faultray.integrations.webhooks.send_pagerduty_event", new_callable=AsyncMock, return_value=False):
            with patch("faultray.api.server._report_to_dict", return_value={}):
                result = runner.invoke(app, [
                    "simulate", "--model", str(model_path),
                    "--pagerduty-key", "test-key",
                ])
                assert result.exit_code == 0

    def test_simulate_webhook_error(self, tmp_path):
        model_path = _create_model_file(tmp_path)
        with patch("faultray.api.server._report_to_dict", return_value={}):
            with patch("faultray.integrations.webhooks.send_slack_notification", new_callable=AsyncMock, side_effect=Exception("connection error")):
                result = runner.invoke(app, [
                    "simulate", "--model", str(model_path),
                    "--slack-webhook", "https://hooks.slack.com/test",
                ])
                assert result.exit_code == 0
                assert "error" in result.output.lower() or "Webhook" in result.output

    def test_simulate_slack_notification_failed(self, tmp_path):
        """Test that slack notification failure (returns False) shows failure message."""
        model_path = _create_model_file(tmp_path)
        with patch("faultray.integrations.webhooks.send_slack_notification", new_callable=AsyncMock, return_value=False):
            with patch("faultray.api.server._report_to_dict", return_value={}):
                result = runner.invoke(app, [
                    "simulate", "--model", str(model_path),
                    "--slack-webhook", "https://hooks.slack.com/test",
                ])
                assert result.exit_code == 0
                assert "failed" in result.output.lower() or "Slack" in result.output

    def test_simulate_with_both_webhooks(self, tmp_path):
        model_path = _create_model_file(tmp_path)
        with patch("faultray.api.server._report_to_dict", return_value={}):
            with patch("faultray.integrations.webhooks.send_slack_notification", new_callable=AsyncMock, return_value=True):
                with patch("faultray.integrations.webhooks.send_pagerduty_event", new_callable=AsyncMock, return_value=True):
                    result = runner.invoke(app, [
                        "simulate", "--model", str(model_path),
                        "--slack-webhook", "https://hooks.slack.com/test",
                        "--pagerduty-key", "test-key",
                    ])
                    assert result.exit_code == 0


# ---------------------------------------------------------------------------
# simulate.py: dynamic command
# ---------------------------------------------------------------------------

class TestDynamicExtended:
    """Tests for dynamic CLI command (simulate.py lines 155-158)."""

    def test_dynamic_with_html(self, tmp_path):
        model_path = _create_model_file(tmp_path)
        html_path = tmp_path / "dynamic-report.html"
        with patch("faultray.reporter.html_report.save_html_report"):
            result = runner.invoke(app, [
                "dynamic", "--model", str(model_path),
                "--duration", "10", "--step", "5",
                "--html", str(html_path),
            ])
            assert result.exit_code == 0

    def test_dynamic_missing_model(self, tmp_path):
        result = runner.invoke(app, [
            "dynamic", "--model", str(tmp_path / "missing.json"),
        ])
        assert result.exit_code != 0


# ---------------------------------------------------------------------------
# analyze.py: error handling branches
# ---------------------------------------------------------------------------

class TestAnalyzeErrors:
    """Tests for analyze.py error handling branches (lines 36-38, 75-77)."""

    def test_analyze_invalid_yaml(self, tmp_path):
        """YAML exists but has invalid component types (ValueError)."""
        bad_yaml = tmp_path / "bad.yaml"
        bad_yaml.write_text("components:\n  - id: x\n    type: invalid_type\n", encoding="utf-8")
        result = runner.invoke(app, ["analyze", str(bad_yaml)])
        assert result.exit_code != 0

    def test_dora_report_invalid_yaml(self, tmp_path):
        """YAML exists but has invalid component types (ValueError)."""
        bad_yaml = tmp_path / "bad.yaml"
        bad_yaml.write_text("components:\n  - id: x\n    type: invalid_type\n", encoding="utf-8")
        result = runner.invoke(app, ["dora-report", str(bad_yaml)])
        assert result.exit_code != 0
