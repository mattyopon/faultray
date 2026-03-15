"""Extended CLI command tests for untested commands.

Covers:
  - antipatterns
  - ab-test
  - autoscale
  - risk
  - carbon
  - fuzz
  - slo-budget
  - ask
  - deps score
  - velocity
  - budget allocate
  - gate check
  - war-room
  - cost-optimize
  - env-compare

Each command is tested for:
  - --help returns exit code 0
  - Basic invocation with a demo model works
  - --json flag produces valid JSON output (where applicable)
  - Invalid input produces error (non-zero exit code)
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from infrasim.cli import app
from infrasim.model.demo import create_demo_graph

runner = CliRunner()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_demo_model(tmp_path: Path) -> Path:
    """Save a demo model to a temp JSON file and return its path.

    NOTE: This produces a JSON file with ``source_id``/``target_id`` keys in
    dependencies.  Commands that pass the file as the ``yaml_file`` argument to
    ``_load_graph_for_analysis`` cannot consume this format -- use
    ``_create_yaml_file`` for those commands instead.
    """
    graph = create_demo_graph()
    model_path = tmp_path / "model.json"
    graph.save(model_path)
    return model_path


def _create_yaml_file(tmp_path: Path) -> Path:
    """Create a YAML infrastructure file compatible with ``load_yaml``."""
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


# ===========================================================================
# 1. antipatterns  (passes arg as yaml_file -> needs YAML)
# ===========================================================================

class TestAntipatterns:
    def test_help(self):
        result = runner.invoke(app, ["antipatterns", "--help"])
        assert result.exit_code == 0
        assert "anti-pattern" in result.output.lower() or "antipattern" in result.output.lower()

    def test_basic(self, tmp_path):
        yaml_path = _create_yaml_file(tmp_path)
        result = runner.invoke(app, ["antipatterns", str(yaml_path)])
        assert result.exit_code == 0

    def test_json_output(self, tmp_path):
        yaml_path = _create_yaml_file(tmp_path)
        result = runner.invoke(app, ["antipatterns", str(yaml_path), "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "total_patterns" in data
        assert "patterns" in data

    def test_invalid_file(self, tmp_path):
        missing = tmp_path / "nonexistent.yaml"
        result = runner.invoke(app, ["antipatterns", str(missing)])
        assert result.exit_code != 0

    def test_min_severity_option(self, tmp_path):
        yaml_path = _create_yaml_file(tmp_path)
        result = runner.invoke(app, ["antipatterns", str(yaml_path), "--min-severity", "critical"])
        assert result.exit_code == 0


# ===========================================================================
# 2. ab-test  (passes args as yaml_file -> needs YAML)
# ===========================================================================

class TestAbTest:
    def test_help(self):
        result = runner.invoke(app, ["ab-test", "--help"])
        assert result.exit_code == 0
        assert "variant" in result.output.lower() or "compare" in result.output.lower()

    def test_basic(self, tmp_path):
        (tmp_path / "a").mkdir()
        yaml_a = _create_yaml_file(tmp_path / "a")
        (tmp_path / "b").mkdir()
        yaml_b = _create_yaml_file(tmp_path / "b")
        result = runner.invoke(app, ["ab-test", "--a", str(yaml_a), "--b", str(yaml_b)])
        assert result.exit_code == 0

    def test_json_output(self, tmp_path):
        (tmp_path / "a").mkdir()
        yaml_a = _create_yaml_file(tmp_path / "a")
        (tmp_path / "b").mkdir()
        yaml_b = _create_yaml_file(tmp_path / "b")
        result = runner.invoke(app, [
            "ab-test", "--a", str(yaml_a), "--b", str(yaml_b), "--json",
        ])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "overall_winner" in data
        assert "variant_a" in data
        assert "variant_b" in data

    def test_invalid_file(self, tmp_path):
        missing_a = tmp_path / "missing_a.yaml"
        missing_b = tmp_path / "missing_b.yaml"
        result = runner.invoke(app, ["ab-test", "--a", str(missing_a), "--b", str(missing_b)])
        assert result.exit_code != 0

    def test_custom_labels(self, tmp_path):
        (tmp_path / "a").mkdir()
        yaml_a = _create_yaml_file(tmp_path / "a")
        (tmp_path / "b").mkdir()
        yaml_b = _create_yaml_file(tmp_path / "b")
        result = runner.invoke(app, [
            "ab-test", "--a", str(yaml_a), "--b", str(yaml_b),
            "--name-a", "v1", "--name-b", "v2",
        ])
        assert result.exit_code == 0


# ===========================================================================
# 3. autoscale  (passes arg as yaml_file -> needs YAML)
# ===========================================================================

class TestAutoscale:
    def test_help(self):
        result = runner.invoke(app, ["autoscale", "--help"])
        assert result.exit_code == 0
        assert "auto-scal" in result.output.lower() or "scaling" in result.output.lower()

    def test_basic(self, tmp_path):
        yaml_path = _create_yaml_file(tmp_path)
        result = runner.invoke(app, ["autoscale", str(yaml_path)])
        assert result.exit_code == 0

    def test_json_output(self, tmp_path):
        yaml_path = _create_yaml_file(tmp_path)
        result = runner.invoke(app, ["autoscale", str(yaml_path), "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)

    def test_invalid_file(self, tmp_path):
        missing = tmp_path / "nonexistent.yaml"
        result = runner.invoke(app, ["autoscale", str(missing)])
        assert result.exit_code != 0

    def test_export_aws(self, tmp_path):
        yaml_path = _create_yaml_file(tmp_path)
        result = runner.invoke(app, ["autoscale", str(yaml_path), "--export", "aws"])
        assert result.exit_code == 0

    def test_export_to_file(self, tmp_path):
        yaml_path = _create_yaml_file(tmp_path)
        output = tmp_path / "hpa.yaml"
        result = runner.invoke(app, ["autoscale", str(yaml_path), "--output", str(output)])
        assert result.exit_code == 0
        assert output.exists()


# ===========================================================================
# 4. risk  (passes arg as yaml_file -> needs YAML)
# ===========================================================================

class TestRisk:
    def test_help(self):
        result = runner.invoke(app, ["risk", "--help"])
        assert result.exit_code == 0
        assert "risk" in result.output.lower()

    def test_basic(self, tmp_path):
        yaml_path = _create_yaml_file(tmp_path)
        result = runner.invoke(app, ["risk", str(yaml_path), "--revenue", "1000000"])
        assert result.exit_code == 0

    def test_json_output(self, tmp_path):
        yaml_path = _create_yaml_file(tmp_path)
        result = runner.invoke(app, ["risk", str(yaml_path), "--revenue", "1000000", "--json"])
        assert result.exit_code == 0
        # The risk command prints a status line before JSON; extract JSON part
        json_start = result.output.index("{")
        data = json.loads(result.output[json_start:])
        assert "expected_annual_loss" in data or "annual_revenue_usd" in data

    def test_invalid_file(self, tmp_path):
        missing = tmp_path / "nonexistent.yaml"
        result = runner.invoke(app, ["risk", str(missing)])
        assert result.exit_code != 0

    def test_custom_revenue(self, tmp_path):
        yaml_path = _create_yaml_file(tmp_path)
        result = runner.invoke(app, ["risk", str(yaml_path), "--revenue", "5000000"])
        assert result.exit_code == 0


# ===========================================================================
# 5. carbon  (passes arg as yaml_file -> needs YAML)
# ===========================================================================

class TestCarbon:
    def test_help(self):
        result = runner.invoke(app, ["carbon", "--help"])
        assert result.exit_code == 0
        assert "carbon" in result.output.lower()

    def test_basic(self, tmp_path):
        yaml_path = _create_yaml_file(tmp_path)
        result = runner.invoke(app, ["carbon", str(yaml_path)])
        assert result.exit_code == 0

    def test_json_output(self, tmp_path):
        yaml_path = _create_yaml_file(tmp_path)
        result = runner.invoke(app, ["carbon", str(yaml_path), "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "total_annual_kg" in data or "sustainability_score" in data

    def test_invalid_file(self, tmp_path):
        missing = tmp_path / "nonexistent.yaml"
        result = runner.invoke(app, ["carbon", str(missing)])
        assert result.exit_code != 0


# ===========================================================================
# 6. fuzz  (passes arg as model -> JSON works)
# ===========================================================================

class TestFuzz:
    def test_help(self):
        result = runner.invoke(app, ["fuzz", "--help"])
        assert result.exit_code == 0
        assert "fuzz" in result.output.lower()

    def test_basic(self, tmp_path):
        model = _create_demo_model(tmp_path)
        result = runner.invoke(app, ["fuzz", str(model), "--iterations", "10"])
        assert result.exit_code == 0

    def test_json_output(self, tmp_path):
        model = _create_demo_model(tmp_path)
        result = runner.invoke(app, ["fuzz", str(model), "--iterations", "10", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "total_iterations" in data
        assert "novel_failures_found" in data

    def test_invalid_file(self, tmp_path):
        missing = tmp_path / "nonexistent.json"
        result = runner.invoke(app, ["fuzz", str(missing)])
        assert result.exit_code != 0

    def test_custom_seed(self, tmp_path):
        model = _create_demo_model(tmp_path)
        result = runner.invoke(app, [
            "fuzz", str(model), "--iterations", "5", "--seed", "99",
        ])
        assert result.exit_code == 0


# ===========================================================================
# 7. slo-budget  (passes arg as model -> JSON works)
# ===========================================================================

class TestSloBudget:
    def test_help(self):
        result = runner.invoke(app, ["slo-budget", "--help"])
        assert result.exit_code == 0
        assert "slo" in result.output.lower()

    def test_basic(self, tmp_path):
        model = _create_demo_model(tmp_path)
        result = runner.invoke(app, ["slo-budget", str(model), "--slo", "99.9"])
        assert result.exit_code == 0

    def test_json_output(self, tmp_path):
        model = _create_demo_model(tmp_path)
        result = runner.invoke(app, [
            "slo-budget", str(model), "--slo", "99.9", "--json",
        ])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "slo_target" in data
        assert "budget_total_minutes" in data

    def test_invalid_file(self, tmp_path):
        missing = tmp_path / "nonexistent.json"
        result = runner.invoke(app, ["slo-budget", str(missing)])
        assert result.exit_code != 0

    def test_custom_window(self, tmp_path):
        model = _create_demo_model(tmp_path)
        result = runner.invoke(app, [
            "slo-budget", str(model), "--slo", "99.9", "--window", "7",
        ])
        assert result.exit_code == 0

    def test_with_consumed(self, tmp_path):
        model = _create_demo_model(tmp_path)
        result = runner.invoke(app, [
            "slo-budget", str(model), "--slo", "99.9", "--consumed", "10",
        ])
        assert result.exit_code == 0


# ===========================================================================
# 8. ask  (uses --model for JSON, or --yaml for YAML)
# ===========================================================================

class TestAsk:
    def test_help(self):
        result = runner.invoke(app, ["ask", "--help"])
        assert result.exit_code == 0
        assert "natural language" in result.output.lower() or "question" in result.output.lower()

    def test_basic(self, tmp_path):
        model = _create_demo_model(tmp_path)
        result = runner.invoke(app, [
            "ask", "what happens if db goes down", "--model", str(model),
        ])
        assert result.exit_code == 0

    def test_json_output(self, tmp_path):
        model = _create_demo_model(tmp_path)
        result = runner.invoke(app, [
            "ask", "what happens if db goes down", "--model", str(model), "--json",
        ])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "query" in data
        assert "answer" in data

    def test_resilience_question(self, tmp_path):
        model = _create_demo_model(tmp_path)
        result = runner.invoke(app, [
            "ask", "how resilient is the system", "--model", str(model),
        ])
        assert result.exit_code == 0

    def test_risk_question(self, tmp_path):
        model = _create_demo_model(tmp_path)
        result = runner.invoke(app, [
            "ask", "what are the biggest risks", "--model", str(model),
        ])
        assert result.exit_code == 0


# ===========================================================================
# 9. deps score  (JSON/YAML auto-detect by extension)
# ===========================================================================

class TestDepsScore:
    def test_help(self):
        result = runner.invoke(app, ["deps", "--help"])
        assert result.exit_code == 0

    def test_score_help(self):
        result = runner.invoke(app, ["deps", "score", "--help"])
        assert result.exit_code == 0
        assert "score" in result.output.lower() or "impact" in result.output.lower()

    def test_score_basic(self, tmp_path):
        model = _create_demo_model(tmp_path)
        result = runner.invoke(app, ["deps", "score", str(model)])
        assert result.exit_code == 0

    def test_score_json_output(self, tmp_path):
        model = _create_demo_model(tmp_path)
        result = runner.invoke(app, ["deps", "score", str(model), "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "total_edges" in data
        assert "dependencies" in data

    def test_score_invalid_file(self, tmp_path):
        missing = tmp_path / "nonexistent.json"
        result = runner.invoke(app, ["deps", "score", str(missing)])
        assert result.exit_code != 0

    def test_score_yaml_input(self, tmp_path):
        yaml_path = _create_yaml_file(tmp_path)
        result = runner.invoke(app, ["deps", "score", str(yaml_path)])
        assert result.exit_code == 0

    def test_score_top_option(self, tmp_path):
        model = _create_demo_model(tmp_path)
        result = runner.invoke(app, ["deps", "score", str(model), "--top", "3"])
        assert result.exit_code == 0


# ===========================================================================
# 10. velocity  (passes arg as model -> JSON works)
# ===========================================================================

class TestVelocity:
    def test_help(self):
        result = runner.invoke(app, ["velocity", "--help"])
        assert result.exit_code == 0
        assert "velocity" in result.output.lower() or "deploy" in result.output.lower()

    def test_basic(self, tmp_path):
        model = _create_demo_model(tmp_path)
        result = runner.invoke(app, [
            "velocity", str(model), "--deploys-per-week", "10",
        ])
        assert result.exit_code == 0

    def test_json_output(self, tmp_path):
        model = _create_demo_model(tmp_path)
        result = runner.invoke(app, [
            "velocity", str(model), "--deploys-per-week", "10", "--json",
        ])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "dora_classification" in data
        assert "stability_impact" in data

    def test_invalid_file(self, tmp_path):
        missing = tmp_path / "nonexistent.json"
        result = runner.invoke(app, ["velocity", str(missing)])
        assert result.exit_code != 0

    def test_sweep_mode(self, tmp_path):
        model = _create_demo_model(tmp_path)
        result = runner.invoke(app, [
            "velocity", str(model), "--sweep", "--json",
        ])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)

    def test_custom_parameters(self, tmp_path):
        model = _create_demo_model(tmp_path)
        result = runner.invoke(app, [
            "velocity", str(model),
            "--deploys-per-week", "50",
            "--cfr", "3",
            "--mttr", "15",
            "--lead-time", "4",
        ])
        assert result.exit_code == 0


# ===========================================================================
# 11. budget allocate  (passes arg as model -> JSON works)
# ===========================================================================

class TestBudgetAllocate:
    def test_help(self):
        result = runner.invoke(app, ["budget", "--help"])
        assert result.exit_code == 0

    def test_basic(self, tmp_path):
        model = _create_demo_model(tmp_path)
        result = runner.invoke(app, ["budget", str(model), "allocate"])
        assert result.exit_code == 0

    def test_json_output(self, tmp_path):
        model = _create_demo_model(tmp_path)
        result = runner.invoke(app, ["budget", str(model), "allocate", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "slo_target" in data
        assert "allocations" in data

    def test_invalid_file(self, tmp_path):
        missing = tmp_path / "nonexistent.json"
        result = runner.invoke(app, ["budget", str(missing)])
        assert result.exit_code != 0

    def test_custom_slo(self, tmp_path):
        model = _create_demo_model(tmp_path)
        result = runner.invoke(app, [
            "budget", str(model), "allocate", "--slo", "99.95",
        ])
        assert result.exit_code == 0


# ===========================================================================
# 12. gate check  (uses --before/--after which go through check_from_files)
# ===========================================================================

class TestGateCheck:
    def test_help(self):
        result = runner.invoke(app, ["gate", "--help"])
        assert result.exit_code == 0

    def test_check_help(self):
        result = runner.invoke(app, ["gate", "check", "--help"])
        assert result.exit_code == 0
        assert "before" in result.output.lower() or "after" in result.output.lower()

    def test_basic(self, tmp_path):
        (tmp_path / "before").mkdir()
        model_before = _create_demo_model(tmp_path / "before")
        (tmp_path / "after").mkdir()
        model_after = _create_demo_model(tmp_path / "after")
        result = runner.invoke(app, [
            "gate", "check",
            "--before", str(model_before),
            "--after", str(model_after),
        ])
        # May be 0 (passed) or 1 (blocked), both are valid behaviors
        assert result.exit_code in (0, 1)

    def test_json_output(self, tmp_path):
        (tmp_path / "before").mkdir()
        model_before = _create_demo_model(tmp_path / "before")
        (tmp_path / "after").mkdir()
        model_after = _create_demo_model(tmp_path / "after")
        result = runner.invoke(app, [
            "gate", "check",
            "--before", str(model_before),
            "--after", str(model_after),
            "--json",
        ])
        # Exit code 0 or 1 are both valid
        assert result.exit_code in (0, 1)
        data = json.loads(result.output)
        assert "passed" in data
        assert "before_score" in data
        assert "after_score" in data

    def test_missing_before(self, tmp_path):
        (tmp_path / "after").mkdir()
        model_after = _create_demo_model(tmp_path / "after")
        missing = tmp_path / "nonexistent.json"
        result = runner.invoke(app, [
            "gate", "check",
            "--before", str(missing),
            "--after", str(model_after),
        ])
        assert result.exit_code != 0

    def test_missing_after(self, tmp_path):
        (tmp_path / "before").mkdir()
        model_before = _create_demo_model(tmp_path / "before")
        missing = tmp_path / "nonexistent.json"
        result = runner.invoke(app, [
            "gate", "check",
            "--before", str(model_before),
            "--after", str(missing),
        ])
        assert result.exit_code != 0


# ===========================================================================
# 13. war-room  (passes arg as model -> JSON works)
# ===========================================================================

class TestWarRoom:
    def test_help(self):
        result = runner.invoke(app, ["war-room", "--help"])
        assert result.exit_code == 0
        assert "war" in result.output.lower() or "incident" in result.output.lower()

    def test_basic(self, tmp_path):
        model = _create_demo_model(tmp_path)
        result = runner.invoke(app, [
            "war-room", str(model), "--incident", "database_outage",
        ])
        assert result.exit_code == 0

    def test_json_output(self, tmp_path):
        model = _create_demo_model(tmp_path)
        result = runner.invoke(app, [
            "war-room", str(model), "--incident", "database_outage", "--json",
        ])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "exercise_name" in data
        assert "score" in data

    def test_invalid_file(self, tmp_path):
        missing = tmp_path / "nonexistent.json"
        result = runner.invoke(app, ["war-room", str(missing)])
        assert result.exit_code != 0

    def test_list_incidents(self, tmp_path):
        model = _create_demo_model(tmp_path)
        result = runner.invoke(app, ["war-room", str(model), "--list"])
        assert result.exit_code == 0
        assert "incident" in result.output.lower() or len(result.output.strip()) > 0

    def test_custom_team_size(self, tmp_path):
        model = _create_demo_model(tmp_path)
        result = runner.invoke(app, [
            "war-room", str(model),
            "--incident", "database_outage",
            "--team-size", "2",
        ])
        assert result.exit_code == 0

    def test_no_runbook(self, tmp_path):
        model = _create_demo_model(tmp_path)
        result = runner.invoke(app, [
            "war-room", str(model),
            "--incident", "database_outage",
            "--no-runbook",
        ])
        assert result.exit_code == 0


# ===========================================================================
# 14. cost-optimize  (passes arg as model -> JSON works)
# ===========================================================================

class TestCostOptimize:
    def test_help(self):
        result = runner.invoke(app, ["cost-optimize", "--help"])
        assert result.exit_code == 0
        assert "cost" in result.output.lower()

    def test_basic(self, tmp_path):
        model = _create_demo_model(tmp_path)
        result = runner.invoke(app, ["cost-optimize", str(model)])
        assert result.exit_code == 0

    def test_json_output(self, tmp_path):
        model = _create_demo_model(tmp_path)
        result = runner.invoke(app, ["cost-optimize", str(model), "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "current_monthly_cost" in data
        assert "suggestions" in data

    def test_invalid_file(self, tmp_path):
        missing = tmp_path / "nonexistent.json"
        result = runner.invoke(app, ["cost-optimize", str(missing)])
        assert result.exit_code != 0

    def test_custom_min_score(self, tmp_path):
        model = _create_demo_model(tmp_path)
        result = runner.invoke(app, ["cost-optimize", str(model), "--min-score", "80"])
        assert result.exit_code == 0


# ===========================================================================
# 15. env-compare  (uses --prod/--staging/--dev YAML files)
# ===========================================================================

class TestEnvCompare:
    def test_help(self):
        result = runner.invoke(app, ["env-compare", "--help"])
        assert result.exit_code == 0
        assert "compare" in result.output.lower() or "environment" in result.output.lower()

    def test_basic(self, tmp_path):
        (tmp_path / "prod").mkdir()
        prod = _create_yaml_file(tmp_path / "prod")
        (tmp_path / "staging").mkdir()
        staging = _create_yaml_file(tmp_path / "staging")
        result = runner.invoke(app, [
            "env-compare", "--prod", str(prod), "--staging", str(staging),
        ])
        assert result.exit_code == 0

    def test_json_output(self, tmp_path):
        (tmp_path / "prod").mkdir()
        prod = _create_yaml_file(tmp_path / "prod")
        (tmp_path / "staging").mkdir()
        staging = _create_yaml_file(tmp_path / "staging")
        result = runner.invoke(app, [
            "env-compare", "--prod", str(prod), "--staging", str(staging), "--json",
        ])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "environments" in data
        assert "parity_score" in data

    def test_insufficient_envs(self, tmp_path):
        (tmp_path / "prod").mkdir()
        prod = _create_yaml_file(tmp_path / "prod")
        result = runner.invoke(app, ["env-compare", "--prod", str(prod)])
        assert result.exit_code != 0

    def test_missing_file(self, tmp_path):
        missing = tmp_path / "missing.yaml"
        (tmp_path / "staging").mkdir()
        staging = _create_yaml_file(tmp_path / "staging")
        result = runner.invoke(app, [
            "env-compare", "--prod", str(missing), "--staging", str(staging),
        ])
        assert result.exit_code != 0

    def test_three_envs(self, tmp_path):
        (tmp_path / "prod").mkdir()
        prod = _create_yaml_file(tmp_path / "prod")
        (tmp_path / "staging").mkdir()
        staging = _create_yaml_file(tmp_path / "staging")
        (tmp_path / "dev").mkdir()
        dev = _create_yaml_file(tmp_path / "dev")
        result = runner.invoke(app, [
            "env-compare",
            "--prod", str(prod),
            "--staging", str(staging),
            "--dev", str(dev),
        ])
        assert result.exit_code == 0
