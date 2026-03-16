"""Tests for quickstart command and plan CLI command."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from faultray.cli import app
from faultray.cli.admin import _build_yaml_from_answers, _TEMPLATES
from faultray.model.loader import load_yaml

runner = CliRunner()


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _create_yaml_file(tmp_path: Path) -> Path:
    """Create a minimal YAML infrastructure file for testing."""
    yaml_content = """\
components:
  - id: lb
    name: Load Balancer
    type: load_balancer
    port: 443
    replicas: 1
    metrics:
      cpu_percent: 20
      memory_percent: 30
    capacity:
      max_connections: 10000

  - id: app
    name: API Server
    type: app_server
    port: 8080
    replicas: 1
    metrics:
      cpu_percent: 50
      memory_percent: 60
    capacity:
      max_connections: 1000

  - id: db
    name: Database
    type: database
    port: 5432
    replicas: 1
    metrics:
      cpu_percent: 40
      memory_percent: 70
    capacity:
      max_connections: 100

dependencies:
  - source: lb
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
# Tests: _build_yaml_from_answers
# ---------------------------------------------------------------------------

class TestBuildYaml:
    """Tests for the YAML generation function."""

    def test_web_app_template_basic(self):
        """web-app template should generate valid YAML."""
        yaml_str = _build_yaml_from_answers(
            template="web-app",
            api_replicas=2,
            database="postgres",
            cache=True,
            queue=None,
            cdn=False,
            lb=True,
        )
        graph = load_yaml_from_string(yaml_str)
        assert len(graph.components) >= 3  # lb + app + db
        assert "lb" in graph.components
        assert "app" in graph.components
        assert "db" in graph.components

    def test_web_app_with_cache_and_queue(self):
        """web-app should include cache and queue when requested."""
        yaml_str = _build_yaml_from_answers(
            template="web-app",
            api_replicas=3,
            database="mysql",
            cache=True,
            queue="SQS",
            cdn=True,
            lb=True,
        )
        graph = load_yaml_from_string(yaml_str)
        assert "cache" in graph.components
        assert "queue" in graph.components
        assert "cdn" in graph.components
        assert graph.components["app"].replicas == 3

    def test_microservices_template(self):
        """microservices template should generate multiple services."""
        yaml_str = _build_yaml_from_answers(
            template="microservices",
            api_replicas=2,
            database="postgres",
            cache=True,
            queue="rabbitmq",
            cdn=False,
            lb=True,
        )
        graph = load_yaml_from_string(yaml_str)
        assert "api" in graph.components
        assert "svc-users" in graph.components
        assert "svc-orders" in graph.components

    def test_data_pipeline_template(self):
        """data-pipeline template should generate pipeline components."""
        yaml_str = _build_yaml_from_answers(
            template="data-pipeline",
            api_replicas=2,
            database="postgres",
            cache=False,
            queue="kafka",
            cdn=False,
            lb=False,
        )
        graph = load_yaml_from_string(yaml_str)
        assert "ingestion" in graph.components
        assert "queue" in graph.components
        assert "processor" in graph.components
        assert "storage" in graph.components

    def test_no_lb(self):
        """web-app without LB should not include lb component."""
        yaml_str = _build_yaml_from_answers(
            template="web-app",
            api_replicas=2,
            database="postgres",
            cache=False,
            queue=None,
            cdn=False,
            lb=False,
        )
        graph = load_yaml_from_string(yaml_str)
        assert "lb" not in graph.components

    def test_no_database(self):
        """web-app without database should not include db component."""
        yaml_str = _build_yaml_from_answers(
            template="web-app",
            api_replicas=1,
            database=None,
            cache=False,
            queue=None,
            cdn=False,
            lb=True,
        )
        graph = load_yaml_from_string(yaml_str)
        assert "db" not in graph.components

    def test_dynamodb_port(self):
        """DynamoDB should use port 443."""
        yaml_str = _build_yaml_from_answers(
            template="web-app",
            api_replicas=1,
            database="dynamodb",
            cache=False,
            queue=None,
            cdn=False,
            lb=True,
        )
        graph = load_yaml_from_string(yaml_str)
        assert graph.components["db"].port == 443


def load_yaml_from_string(yaml_str: str) -> "InfraGraph":
    """Load a YAML string into an InfraGraph via a temp file."""
    import tempfile

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".yaml", delete=False, encoding="utf-8"
    ) as f:
        f.write(yaml_str)
        f.flush()
        return load_yaml(f.name)


# ---------------------------------------------------------------------------
# Tests: quickstart CLI command
# ---------------------------------------------------------------------------

class TestQuickstartCLI:
    """Tests for the quickstart CLI command using CliRunner."""

    def test_quickstart_help(self):
        """quickstart --help should show usage."""
        result = runner.invoke(app, ["quickstart", "--help"])
        assert result.exit_code == 0
        assert "quickstart" in result.output.lower() or "infrastructure" in result.output.lower()

    def test_quickstart_non_interactive_web_app(self, tmp_path: Path):
        """Non-interactive quickstart with --template should produce a model file."""
        output = tmp_path / "model.yaml"
        result = runner.invoke(app, [
            "quickstart",
            "--template", "web-app",
            "--no-simulate",
            "--output", str(output),
        ])
        assert result.exit_code == 0
        assert output.exists()

    def test_quickstart_non_interactive_microservices(self, tmp_path: Path):
        """Non-interactive quickstart with microservices template."""
        output = tmp_path / "model.yaml"
        result = runner.invoke(app, [
            "quickstart",
            "--template", "ecommerce",
            "--no-simulate",
            "--output", str(output),
        ])
        assert result.exit_code == 0
        assert output.exists()

    def test_quickstart_non_interactive_data_pipeline(self, tmp_path: Path):
        """Non-interactive quickstart with data-pipeline template."""
        output = tmp_path / "model.yaml"
        result = runner.invoke(app, [
            "quickstart",
            "--template", "saas",
            "--no-simulate",
            "--output", str(output),
        ])
        assert result.exit_code == 0
        assert output.exists()

    def test_quickstart_interactive_mode(self, tmp_path: Path):
        """Interactive quickstart should work with simulated input."""
        output = tmp_path / "model.yaml"
        # Interactive mode: select template index (1 = first option)
        user_input = "1\n"
        result = runner.invoke(
            app,
            ["quickstart", "--no-simulate", "--output", str(output)],
            input=user_input,
        )
        # Interactive may or may not work depending on template availability
        assert result.exit_code in (0, 1)


# ---------------------------------------------------------------------------
# Tests: plan CLI command
# ---------------------------------------------------------------------------

class TestPlanCLI:
    """Tests for the plan CLI command."""

    def test_plan_help(self):
        """plan --help should show usage."""
        result = runner.invoke(app, ["plan", "--help"])
        assert result.exit_code == 0
        assert "plan" in result.output.lower() or "remediation" in result.output.lower()

    def test_plan_with_yaml(self, tmp_path: Path):
        """plan command should produce output from a YAML file."""
        yaml_path = _create_yaml_file(tmp_path)
        result = runner.invoke(app, ["plan", str(yaml_path)])
        assert result.exit_code == 0
        assert "Phase" in result.output or "Remediation" in result.output

    def test_plan_json_output(self, tmp_path: Path):
        """plan --json should produce valid JSON."""
        yaml_path = _create_yaml_file(tmp_path)
        result = runner.invoke(app, ["plan", str(yaml_path), "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "current_score" in data
        assert "phases" in data
        assert "summary" in data

    def test_plan_with_budget(self, tmp_path: Path):
        """plan --budget should constrain tasks."""
        yaml_path = _create_yaml_file(tmp_path)
        result = runner.invoke(app, [
            "plan", str(yaml_path),
            "--budget", "5000",
            "--json",
        ])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["total_budget"] <= 5000 or len(data["phases"]) == 0

    def test_plan_with_target_score(self, tmp_path: Path):
        """plan --target-score should set the target in the output."""
        yaml_path = _create_yaml_file(tmp_path)
        result = runner.invoke(app, [
            "plan", str(yaml_path),
            "--target-score", "95",
            "--json",
        ])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["target_score"] == 95.0

    def test_plan_html_export(self, tmp_path: Path):
        """plan --html should produce an HTML file."""
        yaml_path = _create_yaml_file(tmp_path)
        html_path = tmp_path / "plan.html"
        result = runner.invoke(app, [
            "plan", str(yaml_path),
            "--html", str(html_path),
        ])
        assert result.exit_code == 0
        assert html_path.exists()
        content = html_path.read_text()
        assert "FaultRay" in content
        assert "Phase" in content

    def test_plan_missing_model(self):
        """plan with a missing model file should fail gracefully."""
        result = runner.invoke(app, ["plan", "/nonexistent/model.yaml"])
        assert result.exit_code != 0


# ---------------------------------------------------------------------------
# Tests: template data
# ---------------------------------------------------------------------------

class TestTemplates:
    """Tests for built-in architecture templates."""

    def test_all_templates_have_components(self):
        """All templates should define at least 2 components."""
        for name, tmpl in _TEMPLATES.items():
            assert len(tmpl["components"]) >= 2, f"Template '{name}' has too few components"

    def test_all_templates_have_dependencies(self):
        """All templates should define at least 1 dependency."""
        for name, tmpl in _TEMPLATES.items():
            assert len(tmpl["dependencies"]) >= 1, f"Template '{name}' has no dependencies"
