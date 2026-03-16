"""Tests for CLI commands using typer.testing.CliRunner."""

from __future__ import annotations

import json
from io import StringIO
from pathlib import Path

import pytest
from typer.testing import CliRunner

from faultray.cli import app
from faultray.model.demo import create_demo_graph

runner = CliRunner()


# ---------------------------------------------------------------------------
# Helper: create a model file from the demo graph
# ---------------------------------------------------------------------------

def _create_model_file(tmp_path: Path) -> Path:
    """Save a demo model to a temp file and return its path."""
    graph = create_demo_graph()
    model_path = tmp_path / "test-model.json"
    graph.save(model_path)
    return model_path


def _create_yaml_file(tmp_path: Path) -> Path:
    """Create a minimal YAML infrastructure file for testing."""
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


# ---------------------------------------------------------------------------
# Help tests
# ---------------------------------------------------------------------------

class TestHelp:
    def test_app_help(self):
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "chaos engineering" in result.output.lower() or "faultray" in result.output.lower()

    def test_demo_help(self):
        result = runner.invoke(app, ["demo", "--help"])
        assert result.exit_code == 0
        assert "demo" in result.output.lower()

    def test_simulate_help(self):
        result = runner.invoke(app, ["simulate", "--help"])
        assert result.exit_code == 0
        assert "simulation" in result.output.lower() or "model" in result.output.lower()

    def test_show_help(self):
        result = runner.invoke(app, ["show", "--help"])
        assert result.exit_code == 0

    def test_analyze_help(self):
        result = runner.invoke(app, ["analyze", "--help"])
        assert result.exit_code == 0

    def test_report_help(self):
        result = runner.invoke(app, ["report", "--help"])
        assert result.exit_code == 0

    def test_scan_help(self):
        result = runner.invoke(app, ["scan", "--help"])
        assert result.exit_code == 0

    def test_serve_help(self):
        result = runner.invoke(app, ["serve", "--help"])
        assert result.exit_code == 0

    def test_feed_update_help(self):
        result = runner.invoke(app, ["feed-update", "--help"])
        assert result.exit_code == 0

    def test_feed_list_help(self):
        result = runner.invoke(app, ["feed-list", "--help"])
        assert result.exit_code == 0


# ---------------------------------------------------------------------------
# Demo command
# ---------------------------------------------------------------------------

class TestDemo:
    def test_demo_runs_successfully(self):
        result = runner.invoke(app, ["demo"])
        assert result.exit_code == 0
        assert "Resilience Score" in result.output

    def test_demo_shows_infrastructure(self):
        result = runner.invoke(app, ["demo"])
        assert result.exit_code == 0
        assert "Infrastructure Overview" in result.output

    def test_demo_shows_critical_or_passed(self):
        result = runner.invoke(app, ["demo"])
        assert result.exit_code == 0
        # Should show at least some simulation results
        has_findings = (
            "CRITICAL" in result.output
            or "WARNING" in result.output
            or "passed" in result.output.lower()
        )
        assert has_findings


# ---------------------------------------------------------------------------
# Simulate command
# ---------------------------------------------------------------------------

class TestSimulate:
    def test_simulate_with_model(self, tmp_path):
        model_path = _create_model_file(tmp_path)
        result = runner.invoke(app, ["simulate", "--model", str(model_path)])
        assert result.exit_code == 0
        assert "Resilience Score" in result.output

    def test_simulate_missing_model(self, tmp_path):
        result = runner.invoke(app, ["simulate", "--model", str(tmp_path / "nonexistent.json")])
        assert result.exit_code != 0

    def test_simulate_with_html_export(self, tmp_path):
        model_path = _create_model_file(tmp_path)
        html_path = tmp_path / "report.html"
        result = runner.invoke(app, ["simulate", "--model", str(model_path), "--html", str(html_path)])
        assert result.exit_code == 0
        assert html_path.exists()
        content = html_path.read_text(encoding="utf-8")
        assert "<html" in content.lower()

    def test_simulate_with_analyze(self, tmp_path):
        model_path = _create_model_file(tmp_path)
        result = runner.invoke(app, ["simulate", "--model", str(model_path), "--analyze"])
        assert result.exit_code == 0
        assert "AI Analysis" in result.output or "Top Risks" in result.output or "Availability" in result.output


# ---------------------------------------------------------------------------
# Show command
# ---------------------------------------------------------------------------

class TestShow:
    def test_show_with_model(self, tmp_path):
        model_path = _create_model_file(tmp_path)
        result = runner.invoke(app, ["show", "--model", str(model_path)])
        assert result.exit_code == 0
        assert "Infrastructure Overview" in result.output
        assert "Components" in result.output

    def test_show_missing_model(self, tmp_path):
        result = runner.invoke(app, ["show", "--model", str(tmp_path / "missing.json")])
        assert result.exit_code != 0


# ---------------------------------------------------------------------------
# Analyze command
# ---------------------------------------------------------------------------

class TestAnalyze:
    def test_analyze_yaml(self, tmp_path):
        yaml_path = _create_yaml_file(tmp_path)
        result = runner.invoke(app, ["analyze", str(yaml_path)])
        assert result.exit_code == 0
        # Should contain AI analysis output
        assert "Resilience Score" in result.output or "Availability" in result.output

    def test_analyze_yaml_json_output(self, tmp_path):
        yaml_path = _create_yaml_file(tmp_path)
        result = runner.invoke(app, ["analyze", str(yaml_path), "--json"])
        assert result.exit_code == 0
        # JSON output should contain key fields
        assert "summary" in result.output or "recommendations" in result.output

    def test_analyze_missing_file(self, tmp_path):
        result = runner.invoke(app, ["analyze", str(tmp_path / "nonexistent.yaml")])
        assert result.exit_code != 0


# ---------------------------------------------------------------------------
# Report command
# ---------------------------------------------------------------------------

class TestReport:
    def test_report_generates_html(self, tmp_path):
        model_path = _create_model_file(tmp_path)
        output_html = tmp_path / "output-report.html"
        result = runner.invoke(app, ["report", "executive", str(model_path), "--output", str(output_html)])
        assert result.exit_code == 0
        assert output_html.exists()

    def test_report_missing_model(self, tmp_path):
        result = runner.invoke(app, ["report", "executive", str(tmp_path / "missing.json")])
        assert result.exit_code != 0


# ---------------------------------------------------------------------------
# Load command
# ---------------------------------------------------------------------------

class TestLoad:
    def test_load_yaml(self, tmp_path):
        yaml_path = _create_yaml_file(tmp_path)
        output = tmp_path / "loaded-model.json"
        result = runner.invoke(app, ["load", str(yaml_path), "--output", str(output)])
        assert result.exit_code == 0
        assert output.exists()
        assert "Model saved" in result.output

    def test_load_missing_yaml(self, tmp_path):
        result = runner.invoke(app, ["load", str(tmp_path / "missing.yaml")])
        assert result.exit_code != 0


# ---------------------------------------------------------------------------
# DORA report command
# ---------------------------------------------------------------------------

class TestDoraReport:
    def test_dora_report_generates_html(self, tmp_path):
        yaml_path = _create_yaml_file(tmp_path)
        output_html = tmp_path / "dora.html"
        result = runner.invoke(app, ["dora-report", str(yaml_path), "--output", str(output_html)])
        assert result.exit_code == 0
        assert output_html.exists()
        content = output_html.read_text(encoding="utf-8")
        assert "DORA" in content

    def test_dora_report_missing_file(self, tmp_path):
        result = runner.invoke(app, ["dora-report", str(tmp_path / "missing.yaml")])
        assert result.exit_code != 0


# ---------------------------------------------------------------------------
# Dynamic command
# ---------------------------------------------------------------------------

class TestDynamic:
    def test_dynamic_missing_model(self, tmp_path):
        result = runner.invoke(app, ["dynamic", "--model", str(tmp_path / "missing.json")])
        assert result.exit_code != 0

    def test_dynamic_with_model(self, tmp_path):
        model_path = _create_model_file(tmp_path)
        result = runner.invoke(app, ["dynamic", "--model", str(model_path), "--duration", "10", "--step", "5"])
        assert result.exit_code == 0
        assert "Dynamic Simulation" in result.output


# ---------------------------------------------------------------------------
# Feed list command (no network needed)
# ---------------------------------------------------------------------------

class TestFeedList:
    def test_feed_list_no_data(self):
        result = runner.invoke(app, ["feed-list"])
        # Should handle gracefully even without feed data
        assert result.exit_code == 0
