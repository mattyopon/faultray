"""Tests for remaining CLI commands that lack coverage.

Covers --help and basic invocation for 20+ commands including plan, template,
compliance-monitor, history, auto-fix, diff, daemon, config, dna, marketplace,
evidence, calendar, twin, replay-timeline, sre-maturity, import-metrics,
git-track, runbook, executive (report), and supply-chain.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from faultray.cli import app

runner = CliRunner()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_model(tmp_path: Path) -> Path:
    """Save a demo model JSON to a temp file and return its path."""
    from faultray.model.demo import create_demo_graph

    g = create_demo_graph()
    p = tmp_path / "m.json"
    g.save(p)
    return p


def _create_yaml(tmp_path: Path) -> Path:
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
    p = tmp_path / "infra.yaml"
    p.write_text(yaml_content, encoding="utf-8")
    return p


def _create_diff_files(tmp_path: Path):
    """Create two simulation result JSON files for diff tests."""
    before = {
        "resilience_score": 70.0,
        "results": [],
        "critical_findings": [],
        "warnings": [],
        "passed": [],
    }
    after = {
        "resilience_score": 75.0,
        "results": [],
        "critical_findings": [],
        "warnings": [],
        "passed": [],
    }
    b = tmp_path / "before.json"
    a = tmp_path / "after.json"
    b.write_text(json.dumps(before), encoding="utf-8")
    a.write_text(json.dumps(after), encoding="utf-8")
    return b, a


# ===================================================================
# 1. plan
# ===================================================================

class TestPlanCommand:
    def test_plan_help(self):
        result = runner.invoke(app, ["plan", "--help"])
        assert result.exit_code == 0
        assert "plan" in result.output.lower() or "remediation" in result.output.lower()

    def test_plan_basic(self, tmp_path):
        model = _create_model(tmp_path)
        result = runner.invoke(app, ["plan", str(model)])
        assert result.exit_code == 0

    def test_plan_json(self, tmp_path):
        model = _create_model(tmp_path)
        result = runner.invoke(app, ["plan", str(model), "--json"])
        assert result.exit_code == 0

    def test_plan_with_target_score(self, tmp_path):
        model = _create_model(tmp_path)
        result = runner.invoke(app, ["plan", str(model), "--target-score", "95"])
        assert result.exit_code == 0

    def test_plan_with_budget(self, tmp_path):
        model = _create_model(tmp_path)
        result = runner.invoke(app, ["plan", str(model), "--budget", "50000"])
        assert result.exit_code == 0

    def test_plan_html_export(self, tmp_path):
        model = _create_model(tmp_path)
        html_out = tmp_path / "plan.html"
        result = runner.invoke(app, ["plan", str(model), "--html", str(html_out)])
        assert result.exit_code == 0
        assert html_out.exists()


# ===================================================================
# 2. template list / template use
# ===================================================================

class TestTemplateCommand:
    def test_template_help(self):
        result = runner.invoke(app, ["template", "--help"])
        assert result.exit_code == 0

    def test_template_list_help(self):
        result = runner.invoke(app, ["template", "list", "--help"])
        assert result.exit_code == 0

    def test_template_list(self):
        result = runner.invoke(app, ["template", "list"])
        assert result.exit_code == 0

    def test_template_use_help(self):
        result = runner.invoke(app, ["template", "use", "--help"])
        assert result.exit_code == 0

    def test_template_use_gallery(self, tmp_path):
        # Try using a gallery template; even if it fails with unknown, it should not crash
        out_file = tmp_path / "out.yaml"
        result = runner.invoke(app, ["template", "use", "ha-web-3tier", "--output", str(out_file)])
        # Either succeeds or exits with template not found (exit code 1)
        assert result.exit_code in (0, 1)

    def test_template_info_help(self):
        result = runner.invoke(app, ["template", "info", "--help"])
        assert result.exit_code == 0

    def test_template_compare_help(self):
        result = runner.invoke(app, ["template", "compare", "--help"])
        assert result.exit_code == 0


# ===================================================================
# 3. compliance-monitor --snapshot
# ===================================================================

class TestComplianceMonitorCommand:
    def test_compliance_monitor_help(self):
        result = runner.invoke(app, ["compliance-monitor", "--help"])
        assert result.exit_code == 0
        assert "compliance" in result.output.lower()

    def test_compliance_monitor_snapshot(self, tmp_path):
        yaml_path = _create_yaml(tmp_path)
        result = runner.invoke(app, [
            "compliance-monitor", str(yaml_path),
            "--framework", "soc2",
            "--snapshot",
        ])
        assert result.exit_code == 0

    def test_compliance_monitor_default_assess(self, tmp_path):
        yaml_path = _create_yaml(tmp_path)
        result = runner.invoke(app, [
            "compliance-monitor", str(yaml_path),
            "--framework", "soc2",
        ])
        assert result.exit_code == 0

    def test_compliance_monitor_json(self, tmp_path):
        yaml_path = _create_yaml(tmp_path)
        result = runner.invoke(app, [
            "compliance-monitor", str(yaml_path),
            "--framework", "soc2",
            "--json",
        ])
        assert result.exit_code == 0

    def test_compliance_monitor_snapshot_all_frameworks(self, tmp_path):
        yaml_path = _create_yaml(tmp_path)
        result = runner.invoke(app, [
            "compliance-monitor", str(yaml_path),
            "--snapshot",
        ])
        assert result.exit_code == 0

    def test_compliance_monitor_invalid_framework(self, tmp_path):
        yaml_path = _create_yaml(tmp_path)
        result = runner.invoke(app, [
            "compliance-monitor", str(yaml_path),
            "--framework", "invalid_fw",
        ])
        assert result.exit_code == 1


# ===================================================================
# 4. history
# ===================================================================

class TestHistoryCommand:
    def test_history_help(self):
        result = runner.invoke(app, ["history", "--help"])
        assert result.exit_code == 0
        assert "history" in result.output.lower() or "trend" in result.output.lower()

    def test_history_basic(self, tmp_path):
        # Without data, should still not crash
        result = runner.invoke(app, ["history", "--db", str(tmp_path / "h.db")])
        assert result.exit_code == 0

    def test_history_json(self, tmp_path):
        result = runner.invoke(app, ["history", "--json", "--db", str(tmp_path / "h.db")])
        assert result.exit_code == 0

    def test_history_custom_days(self, tmp_path):
        result = runner.invoke(app, ["history", "--days", "30", "--db", str(tmp_path / "h.db")])
        assert result.exit_code == 0


# ===================================================================
# 5. auto-fix --dry-run
# ===================================================================

class TestAutoFixCommand:
    def test_auto_fix_help(self):
        result = runner.invoke(app, ["auto-fix", "--help"])
        assert result.exit_code == 0
        assert "auto-fix" in result.output.lower() or "remediation" in result.output.lower()

    def test_auto_fix_dry_run(self, tmp_path):
        model = _create_model(tmp_path)
        result = runner.invoke(app, ["auto-fix", str(model), "--dry-run"])
        assert result.exit_code == 0

    def test_auto_fix_json(self, tmp_path):
        model = _create_model(tmp_path)
        result = runner.invoke(app, ["auto-fix", str(model), "--json"])
        assert result.exit_code == 0

    def test_auto_fix_target_score(self, tmp_path):
        model = _create_model(tmp_path)
        result = runner.invoke(app, ["auto-fix", str(model), "--target-score", "85"])
        assert result.exit_code == 0


# ===================================================================
# 6. diff
# ===================================================================

class TestDiffCommand:
    def test_diff_help(self):
        result = runner.invoke(app, ["diff", "--help"])
        assert result.exit_code == 0
        assert "diff" in result.output.lower()

    def test_diff_basic(self, tmp_path):
        b, a = _create_diff_files(tmp_path)
        result = runner.invoke(app, ["diff", str(b), str(a)])
        assert result.exit_code in (0, 1)  # may flag regression

    def test_diff_json(self, tmp_path):
        b, a = _create_diff_files(tmp_path)
        result = runner.invoke(app, ["diff", str(b), str(a), "--json"])
        assert result.exit_code in (0, 1)

    def test_diff_missing_before(self, tmp_path):
        _, a = _create_diff_files(tmp_path)
        result = runner.invoke(app, ["diff", str(tmp_path / "nonexistent.json"), str(a)])
        assert result.exit_code == 1

    def test_diff_missing_after(self, tmp_path):
        b, _ = _create_diff_files(tmp_path)
        result = runner.invoke(app, ["diff", str(b), str(tmp_path / "nonexistent.json")])
        assert result.exit_code == 1


# ===================================================================
# 7. daemon --help
# ===================================================================

class TestDaemonCommand:
    def test_daemon_help(self):
        result = runner.invoke(app, ["daemon", "--help"])
        assert result.exit_code == 0
        assert "daemon" in result.output.lower()

    def test_daemon_missing_model(self, tmp_path):
        result = runner.invoke(app, ["daemon", "--model", str(tmp_path / "nope.json")])
        assert result.exit_code == 1


# ===================================================================
# 8. config show
# ===================================================================

class TestConfigCommand:
    def test_config_help(self):
        result = runner.invoke(app, ["config", "--help"])
        assert result.exit_code == 0

    def test_config_show_help(self):
        result = runner.invoke(app, ["config", "show", "--help"])
        assert result.exit_code == 0

    def test_config_show(self, tmp_path):
        cfg_path = tmp_path / "cfg.yaml"
        result = runner.invoke(app, ["config", "show", "--path", str(cfg_path)])
        assert result.exit_code == 0

    def test_config_set_help(self):
        result = runner.invoke(app, ["config", "set", "--help"])
        assert result.exit_code == 0

    def test_config_set(self, tmp_path):
        cfg_path = tmp_path / "cfg.yaml"
        result = runner.invoke(app, ["config", "set", "ui.theme", "dark", "--path", str(cfg_path)])
        assert result.exit_code == 0


# ===================================================================
# 9. dna fingerprint
# ===================================================================

class TestDnaCommand:
    def test_dna_help(self):
        result = runner.invoke(app, ["dna", "--help"])
        assert result.exit_code == 0
        assert "dna" in result.output.lower() or "fingerprint" in result.output.lower()

    def test_dna_fingerprint(self, tmp_path):
        yaml_path = _create_yaml(tmp_path)
        result = runner.invoke(app, ["dna", "fingerprint", str(yaml_path)])
        assert result.exit_code == 0

    def test_dna_fingerprint_json(self, tmp_path):
        yaml_path = _create_yaml(tmp_path)
        result = runner.invoke(app, ["dna", "fingerprint", str(yaml_path), "--json"])
        assert result.exit_code == 0

    def test_dna_compare(self, tmp_path):
        y1 = _create_yaml(tmp_path)
        y2 = tmp_path / "infra2.yaml"
        y2.write_text(y1.read_text(), encoding="utf-8")
        result = runner.invoke(app, ["dna", "compare", str(y1), str(y2)])
        assert result.exit_code == 0

    def test_dna_compare_json(self, tmp_path):
        y1 = _create_yaml(tmp_path)
        y2 = tmp_path / "infra2.yaml"
        y2.write_text(y1.read_text(), encoding="utf-8")
        result = runner.invoke(app, ["dna", "compare", str(y1), str(y2), "--json"])
        assert result.exit_code == 0

    def test_dna_compare_missing_second(self, tmp_path):
        yaml_path = _create_yaml(tmp_path)
        result = runner.invoke(app, ["dna", "compare", str(yaml_path)])
        assert result.exit_code == 1

    def test_dna_unknown_action(self, tmp_path):
        yaml_path = _create_yaml(tmp_path)
        result = runner.invoke(app, ["dna", "nope", str(yaml_path)])
        assert result.exit_code == 1


# ===================================================================
# 10. marketplace list
# ===================================================================

class TestMarketplaceCommand:
    def test_marketplace_help(self):
        result = runner.invoke(app, ["marketplace", "--help"])
        assert result.exit_code == 0

    def test_marketplace_list(self):
        result = runner.invoke(app, ["marketplace", "list"])
        assert result.exit_code == 0

    def test_marketplace_list_json(self):
        result = runner.invoke(app, ["marketplace", "list", "--json"])
        assert result.exit_code == 0

    def test_marketplace_categories(self):
        result = runner.invoke(app, ["marketplace", "categories"])
        assert result.exit_code == 0

    def test_marketplace_featured(self):
        result = runner.invoke(app, ["marketplace", "featured"])
        assert result.exit_code == 0

    def test_marketplace_popular(self):
        result = runner.invoke(app, ["marketplace", "popular"])
        assert result.exit_code == 0

    def test_marketplace_new(self):
        result = runner.invoke(app, ["marketplace", "new"])
        assert result.exit_code == 0

    def test_marketplace_search(self):
        result = runner.invoke(app, ["marketplace", "search", "database"])
        assert result.exit_code == 0

    def test_marketplace_search_no_query(self):
        result = runner.invoke(app, ["marketplace", "search"])
        assert result.exit_code == 1

    def test_marketplace_unknown_action(self):
        result = runner.invoke(app, ["marketplace", "bogus"])
        assert result.exit_code == 1


# ===================================================================
# 11. evidence generate --framework SOC2
# ===================================================================

class TestEvidenceCommand:
    def test_evidence_help(self):
        result = runner.invoke(app, ["evidence", "--help"])
        assert result.exit_code == 0

    def test_evidence_generate_help(self):
        result = runner.invoke(app, ["evidence", "generate", "--help"])
        assert result.exit_code == 0

    def test_evidence_generate(self, tmp_path):
        yaml_path = _create_yaml(tmp_path)
        result = runner.invoke(app, [
            "evidence", "generate", str(yaml_path),
            "--framework", "SOC2",
        ])
        assert result.exit_code == 0

    def test_evidence_generate_json(self, tmp_path):
        yaml_path = _create_yaml(tmp_path)
        result = runner.invoke(app, [
            "evidence", "generate", str(yaml_path),
            "--framework", "SOC2",
            "--json",
        ])
        assert result.exit_code == 0

    def test_evidence_generate_csv(self, tmp_path):
        yaml_path = _create_yaml(tmp_path)
        csv_out = tmp_path / "evidence.csv"
        result = runner.invoke(app, [
            "evidence", "generate", str(yaml_path),
            "--framework", "SOC2",
            "--output", str(csv_out),
        ])
        assert result.exit_code == 0

    def test_evidence_generate_with_simulate(self, tmp_path):
        yaml_path = _create_yaml(tmp_path)
        result = runner.invoke(app, [
            "evidence", "generate", str(yaml_path),
            "--framework", "SOC2",
            "--simulate",
        ])
        assert result.exit_code == 0

    def test_evidence_frameworks(self):
        result = runner.invoke(app, ["evidence", "frameworks"])
        assert result.exit_code == 0

    def test_evidence_generate_dora(self, tmp_path):
        yaml_path = _create_yaml(tmp_path)
        result = runner.invoke(app, [
            "evidence", "generate", str(yaml_path),
            "--framework", "DORA",
        ])
        assert result.exit_code == 0


# ===================================================================
# 12. calendar suggest
# ===================================================================

class TestCalendarCommand:
    def test_calendar_help(self):
        result = runner.invoke(app, ["calendar", "--help"])
        assert result.exit_code == 0

    def test_calendar_suggest_help(self):
        result = runner.invoke(app, ["calendar", "suggest", "--help"])
        assert result.exit_code == 0

    def test_calendar_suggest(self, tmp_path):
        yaml_path = _create_yaml(tmp_path)
        result = runner.invoke(app, ["calendar", "suggest", str(yaml_path)])
        assert result.exit_code == 0

    def test_calendar_suggest_json(self, tmp_path):
        yaml_path = _create_yaml(tmp_path)
        result = runner.invoke(app, ["calendar", "suggest", str(yaml_path), "--json"])
        assert result.exit_code == 0

    def test_calendar_forecast(self, tmp_path):
        yaml_path = _create_yaml(tmp_path)
        result = runner.invoke(app, ["calendar", "forecast", str(yaml_path)])
        assert result.exit_code == 0

    def test_calendar_forecast_json(self, tmp_path):
        yaml_path = _create_yaml(tmp_path)
        result = runner.invoke(app, ["calendar", "forecast", str(yaml_path), "--json"])
        assert result.exit_code == 0

    def test_calendar_schedule(self, tmp_path):
        yaml_path = _create_yaml(tmp_path)
        result = runner.invoke(app, ["calendar", "schedule", str(yaml_path)])
        assert result.exit_code == 0

    def test_calendar_show(self):
        result = runner.invoke(app, ["calendar", "show"])
        assert result.exit_code == 0

    def test_calendar_show_json(self):
        result = runner.invoke(app, ["calendar", "show", "--json"])
        assert result.exit_code == 0

    def test_calendar_history_cmd(self):
        result = runner.invoke(app, ["calendar", "history"])
        assert result.exit_code == 0

    def test_calendar_coverage(self, tmp_path):
        yaml_path = _create_yaml(tmp_path)
        result = runner.invoke(app, ["calendar", "coverage", str(yaml_path)])
        assert result.exit_code == 0

    def test_calendar_export(self, tmp_path):
        out = tmp_path / "calendar.ics"
        result = runner.invoke(app, ["calendar", "export", "--output", str(out)])
        assert result.exit_code == 0

    def test_calendar_export_json(self):
        result = runner.invoke(app, ["calendar", "export", "--json"])
        assert result.exit_code == 0


# ===================================================================
# 13. twin predict
# ===================================================================

class TestTwinCommand:
    def test_twin_help(self):
        result = runner.invoke(app, ["twin", "--help"])
        assert result.exit_code == 0

    def test_twin_predict_help(self):
        result = runner.invoke(app, ["twin", "predict", "--help"])
        assert result.exit_code == 0

    def test_twin_predict(self, tmp_path):
        yaml_path = _create_yaml(tmp_path)
        result = runner.invoke(app, ["twin", "predict", str(yaml_path)])
        assert result.exit_code == 0

    def test_twin_predict_json(self, tmp_path):
        yaml_path = _create_yaml(tmp_path)
        result = runner.invoke(app, ["twin", "predict", str(yaml_path), "--json"])
        assert result.exit_code == 0

    def test_twin_predict_horizon(self, tmp_path):
        yaml_path = _create_yaml(tmp_path)
        result = runner.invoke(app, ["twin", "predict", str(yaml_path), "--horizon", "120"])
        assert result.exit_code == 0


# ===================================================================
# 14. replay-timeline --help
# ===================================================================

class TestReplayTimelineCommand:
    def test_replay_timeline_help(self):
        result = runner.invoke(app, ["replay-timeline", "--help"])
        assert result.exit_code == 0
        assert "replay" in result.output.lower() or "incident" in result.output.lower()

    def test_replay_timeline_basic(self, tmp_path):
        yaml_path = _create_yaml(tmp_path)
        # Create a minimal incident file
        incident = {
            "incident_id": "INC-TEST-001",
            "title": "Test Incident",
            "root_cause": "Test",
            "duration_minutes": 30,
            "severity": 7.0,
            "events": [
                {
                    "timestamp_offset_seconds": 0,
                    "event_type": "component_down",
                    "component_id": "db",
                    "details": "DB crash",
                },
            ],
        }
        incident_file = tmp_path / "incident.json"
        incident_file.write_text(json.dumps(incident), encoding="utf-8")
        result = runner.invoke(app, [
            "replay-timeline", str(yaml_path),
            "--incident", str(incident_file),
        ])
        assert result.exit_code == 0

    def test_replay_timeline_json(self, tmp_path):
        yaml_path = _create_yaml(tmp_path)
        incident = {
            "incident_id": "INC-TEST-002",
            "title": "Incident X",
            "root_cause": "Unknown",
            "duration_minutes": 15,
            "severity": 5.0,
            "events": [
                {
                    "timestamp_offset_seconds": 0,
                    "event_type": "component_down",
                    "component_id": "app",
                    "details": "App crash",
                },
            ],
        }
        incident_file = tmp_path / "inc.json"
        incident_file.write_text(json.dumps(incident), encoding="utf-8")
        result = runner.invoke(app, [
            "replay-timeline", str(yaml_path),
            "--incident", str(incident_file),
            "--json",
        ])
        assert result.exit_code == 0


# ===================================================================
# 15. sre-maturity
# ===================================================================

class TestSreMaturityCommand:
    def test_sre_maturity_help(self):
        result = runner.invoke(app, ["sre-maturity", "--help"])
        assert result.exit_code == 0
        assert "maturity" in result.output.lower()

    def test_sre_maturity_basic(self, tmp_path):
        yaml_path = _create_yaml(tmp_path)
        result = runner.invoke(app, ["sre-maturity", str(yaml_path)])
        assert result.exit_code == 0

    def test_sre_maturity_json(self, tmp_path):
        yaml_path = _create_yaml(tmp_path)
        result = runner.invoke(app, ["sre-maturity", str(yaml_path), "--json"])
        assert result.exit_code == 0

    def test_sre_maturity_roadmap(self, tmp_path):
        yaml_path = _create_yaml(tmp_path)
        result = runner.invoke(app, ["sre-maturity", str(yaml_path), "--roadmap"])
        assert result.exit_code == 0

    def test_sre_maturity_dimension(self, tmp_path):
        yaml_path = _create_yaml(tmp_path)
        result = runner.invoke(app, [
            "sre-maturity", str(yaml_path),
            "--dimension", "monitoring",
        ])
        assert result.exit_code == 0

    def test_sre_maturity_dimension_json(self, tmp_path):
        yaml_path = _create_yaml(tmp_path)
        result = runner.invoke(app, [
            "sre-maturity", str(yaml_path),
            "--dimension", "monitoring",
            "--json",
        ])
        assert result.exit_code == 0


# ===================================================================
# 16. import-metrics --help
# ===================================================================

class TestImportMetricsCommand:
    def test_import_metrics_help(self):
        result = runner.invoke(app, ["import-metrics", "--help"])
        assert result.exit_code == 0
        assert "import" in result.output.lower() or "metrics" in result.output.lower()

    def test_import_metrics_no_source(self, tmp_path):
        yaml_path = _create_yaml(tmp_path)
        result = runner.invoke(app, ["import-metrics", str(yaml_path)])
        assert result.exit_code == 1  # should fail: no source specified

    def test_import_metrics_json_file(self, tmp_path):
        yaml_path = _create_yaml(tmp_path)
        metrics_file = tmp_path / "metrics.json"
        metrics = {
            "metrics": [
                {"component_id": "web", "metric": "cpu_percent", "value": 55.0},
                {"component_id": "app", "metric": "memory_percent", "value": 75.0},
            ]
        }
        metrics_file.write_text(json.dumps(metrics), encoding="utf-8")
        result = runner.invoke(app, [
            "import-metrics", str(yaml_path),
            "--json-file", str(metrics_file),
        ])
        assert result.exit_code == 0

    def test_import_metrics_json_file_json_output(self, tmp_path):
        yaml_path = _create_yaml(tmp_path)
        metrics_file = tmp_path / "metrics.json"
        metrics = {"metrics": []}
        metrics_file.write_text(json.dumps(metrics), encoding="utf-8")
        result = runner.invoke(app, [
            "import-metrics", str(yaml_path),
            "--json-file", str(metrics_file),
            "--json",
        ])
        assert result.exit_code == 0


# ===================================================================
# 17. git-track --help
# ===================================================================

class TestGitTrackCommand:
    def test_git_track_help(self):
        result = runner.invoke(app, ["git-track", "--help"])
        assert result.exit_code == 0
        assert "git" in result.output.lower() or "track" in result.output.lower()


# ===================================================================
# 18. runbook validate --help
# ===================================================================

class TestRunbookCommand:
    def test_runbook_help(self):
        result = runner.invoke(app, ["runbook", "--help"])
        assert result.exit_code == 0

    def test_runbook_validate_help(self):
        result = runner.invoke(app, ["runbook", "validate", "--help"])
        assert result.exit_code == 0
        assert "validate" in result.output.lower()


# ===================================================================
# 19. executive (report executive) --help
# ===================================================================

class TestExecutiveReportCommand:
    def test_report_help(self):
        result = runner.invoke(app, ["report", "--help"])
        assert result.exit_code == 0

    def test_report_executive(self, tmp_path):
        yaml_path = _create_yaml(tmp_path)
        html_out = tmp_path / "exec.html"
        result = runner.invoke(app, [
            "report", "executive", str(yaml_path),
            "--output", str(html_out),
        ])
        assert result.exit_code == 0

    def test_report_compliance(self, tmp_path):
        yaml_path = _create_yaml(tmp_path)
        result = runner.invoke(app, [
            "report", "compliance", str(yaml_path),
            "--json",
        ])
        assert result.exit_code == 0

    def test_report_compliance_framework(self, tmp_path):
        yaml_path = _create_yaml(tmp_path)
        result = runner.invoke(app, [
            "report", "compliance", str(yaml_path),
            "--framework", "soc2",
            "--json",
        ])
        assert result.exit_code == 0


# ===================================================================
# 20. supply-chain --help
# ===================================================================

class TestSupplyChainCommand:
    def test_supply_chain_help(self):
        result = runner.invoke(app, ["supply-chain", "--help"])
        assert result.exit_code == 0
        assert "supply" in result.output.lower() or "chain" in result.output.lower()

    def test_supply_chain_basic(self, tmp_path):
        yaml_path = _create_yaml(tmp_path)
        # Create a minimal vulnerability report
        vulns = {
            "vulnerabilities": [
                {
                    "id": "CVE-2024-0001",
                    "severity": "high",
                    "package": "openssl",
                    "version": "1.1.1",
                    "title": "Buffer overflow in OpenSSL",
                },
            ]
        }
        vulns_file = tmp_path / "vulns.json"
        vulns_file.write_text(json.dumps(vulns), encoding="utf-8")
        result = runner.invoke(app, [
            "supply-chain", str(yaml_path),
            "--vulns", str(vulns_file),
        ])
        assert result.exit_code == 0

    def test_supply_chain_json(self, tmp_path):
        yaml_path = _create_yaml(tmp_path)
        vulns = {"vulnerabilities": []}
        vulns_file = tmp_path / "vulns.json"
        vulns_file.write_text(json.dumps(vulns), encoding="utf-8")
        result = runner.invoke(app, [
            "supply-chain", str(yaml_path),
            "--vulns", str(vulns_file),
            "--json",
        ])
        assert result.exit_code == 0

    def test_supply_chain_missing_vulns(self, tmp_path):
        yaml_path = _create_yaml(tmp_path)
        result = runner.invoke(app, [
            "supply-chain", str(yaml_path),
            "--vulns", str(tmp_path / "nope.json"),
        ])
        assert result.exit_code == 1


# ===================================================================
# Extra: additional commands for coverage
# ===================================================================

class TestExtraCommands:
    """Additional CLI commands for extra coverage."""

    def test_evaluate_help(self):
        result = runner.invoke(app, ["evaluate", "--help"])
        assert result.exit_code == 0

    def test_simulate_help(self):
        result = runner.invoke(app, ["simulate", "--help"])
        assert result.exit_code == 0

    def test_demo_help(self):
        result = runner.invoke(app, ["demo", "--help"])
        assert result.exit_code == 0

    def test_serve_help(self):
        result = runner.invoke(app, ["serve", "--help"])
        assert result.exit_code == 0

    def test_genome_help(self):
        result = runner.invoke(app, ["genome", "--help"])
        assert result.exit_code == 0

    def test_benchmark_help(self):
        result = runner.invoke(app, ["benchmark", "--help"])
        assert result.exit_code == 0

    def test_sla_validate_help(self):
        result = runner.invoke(app, ["sla-validate", "--help"])
        assert result.exit_code == 0

    def test_drift_help(self):
        result = runner.invoke(app, ["drift", "--help"])
        assert result.exit_code == 0

    def test_advisor_help(self):
        result = runner.invoke(app, ["advisor", "--help"])
        assert result.exit_code in (0, 2)  # subcommand group: no_args_is_help

    def test_replay_help(self):
        result = runner.invoke(app, ["replay", "--help"])
        assert result.exit_code == 0

    def test_fuzz_help(self):
        result = runner.invoke(app, ["fuzz", "--help"])
        assert result.exit_code == 0

    def test_ask_help(self):
        result = runner.invoke(app, ["ask", "--help"])
        assert result.exit_code == 0

    def test_deps_help(self):
        result = runner.invoke(app, ["deps", "--help"])
        assert result.exit_code == 0

    def test_heatmap_help(self):
        result = runner.invoke(app, ["heatmap", "--help"])
        assert result.exit_code == 0

    def test_contract_help(self):
        result = runner.invoke(app, ["contract", "--help"])
        assert result.exit_code in (0, 2)

    def test_canary_help(self):
        result = runner.invoke(app, ["canary", "--help"])
        assert result.exit_code in (0, 2)

    def test_topology_diff_help(self):
        result = runner.invoke(app, ["topology-diff", "--help"])
        assert result.exit_code in (0, 2)

    def test_anomaly_help(self):
        result = runner.invoke(app, ["anomaly", "--help"])
        assert result.exit_code == 0

    def test_postmortem_help(self):
        result = runner.invoke(app, ["postmortem", "--help"])
        assert result.exit_code in (0, 2)

    def test_env_compare_help(self):
        result = runner.invoke(app, ["env-compare", "--help"])
        assert result.exit_code == 0

    def test_war_room_help(self):
        result = runner.invoke(app, ["war-room", "--help"])
        assert result.exit_code == 0

    def test_cost_optimize_help(self):
        result = runner.invoke(app, ["cost-optimize", "--help"])
        assert result.exit_code == 0

    def test_antipattern_help(self):
        result = runner.invoke(app, ["antipattern", "--help"])
        assert result.exit_code in (0, 2)

    def test_fmea_help(self):
        result = runner.invoke(app, ["fmea", "--help"])
        assert result.exit_code == 0

    def test_monkey_help(self):
        result = runner.invoke(app, ["monkey", "--help"])
        assert result.exit_code in (0, 2)

    def test_budget_help(self):
        result = runner.invoke(app, ["budget", "--help"])
        assert result.exit_code == 0

    def test_velocity_help(self):
        result = runner.invoke(app, ["velocity", "--help"])
        assert result.exit_code == 0

    def test_attack_surface_help(self):
        result = runner.invoke(app, ["attack-surface", "--help"])
        assert result.exit_code == 0

    def test_score_help(self):
        result = runner.invoke(app, ["score", "--help"])
        assert result.exit_code in (0, 2)

    def test_ab_test_help(self):
        result = runner.invoke(app, ["ab-test", "--help"])
        assert result.exit_code == 0

    def test_gate_help(self):
        result = runner.invoke(app, ["gate", "--help"])
        assert result.exit_code == 0

    def test_team_help(self):
        result = runner.invoke(app, ["team", "--help"])
        assert result.exit_code == 0

    def test_plugin_help(self):
        result = runner.invoke(app, ["plugin", "--help"])
        assert result.exit_code == 0

    def test_slo_budget_help(self):
        result = runner.invoke(app, ["slo-budget", "--help"])
        assert result.exit_code == 0

    def test_graph_export_help(self):
        result = runner.invoke(app, ["graph-export", "--help"])
        assert result.exit_code == 0

    def test_multienv_help(self):
        result = runner.invoke(app, ["multienv", "--help"])
        assert result.exit_code in (0, 2)

    def test_cost_attr_help(self):
        result = runner.invoke(app, ["cost-attribution", "--help"])
        assert result.exit_code == 0

    def test_timeline_help(self):
        result = runner.invoke(app, ["timeline", "--help"])
        assert result.exit_code == 0

    def test_predictive_help(self):
        result = runner.invoke(app, ["predictive", "--help"])
        assert result.exit_code in (0, 2)

    def test_autoscale_help(self):
        result = runner.invoke(app, ["autoscale", "--help"])
        assert result.exit_code == 0

    def test_optimizer_help(self):
        result = runner.invoke(app, ["optimizer", "--help"])
        assert result.exit_code in (0, 2)

    def test_backtest_help(self):
        result = runner.invoke(app, ["backtest", "--help"])
        assert result.exit_code == 0

    def test_feeds_help(self):
        result = runner.invoke(app, ["feeds", "--help"])
        assert result.exit_code in (0, 2)

    def test_scan_help(self):
        result = runner.invoke(app, ["scan", "--help"])
        assert result.exit_code == 0

    def test_load_help(self):
        result = runner.invoke(app, ["load", "--help"])
        assert result.exit_code == 0

    def test_export_help(self):
        result = runner.invoke(app, ["export", "--help"])
        assert result.exit_code == 0
