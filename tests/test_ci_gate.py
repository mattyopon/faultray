"""Tests for CI/CD resilience gate and SARIF exporter."""

from __future__ import annotations

import json

import pytest
import yaml

from faultray.ci.github_action import CIGateConfig, CIGateGenerator
from faultray.ci.sarif_exporter import (
    SARIFExporter,
    export_sarif,
    _risk_to_sarif_level,
    _risk_to_severity,
    _get_remediation,
)
from faultray.model.components import (
    Component,
    ComponentType,
    Dependency,
    OperationalProfile,
)
from faultray.model.graph import InfraGraph
from faultray.simulator.engine import (
    CascadeChain,
    ScenarioResult,
    SimulationEngine,
    SimulationReport,
)
from faultray.simulator.scenarios import Scenario


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _simple_graph() -> InfraGraph:
    """Build a simple 3-component graph: LB -> App -> DB."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="lb", name="LB", type=ComponentType.LOAD_BALANCER, replicas=2,
    ))
    graph.add_component(Component(
        id="app", name="App", type=ComponentType.APP_SERVER, replicas=3,
    ))
    graph.add_component(Component(
        id="db", name="DB", type=ComponentType.DATABASE, replicas=1,
    ))
    graph.add_dependency(Dependency(
        source_id="lb", target_id="app", dependency_type="requires",
    ))
    graph.add_dependency(Dependency(
        source_id="app", target_id="db", dependency_type="requires",
    ))
    return graph


def _simple_report() -> SimulationReport:
    """Build a minimal SimulationReport with mixed results."""
    results = [
        ScenarioResult(
            scenario=Scenario(
                id="s1", name="Single point of failure: db",
                description="SPOF in database layer",
                faults=[], traffic_multiplier=1.0,
            ),
            cascade=CascadeChain(trigger="SPOF: db", total_components=3),
            risk_score=8.5,
        ),
        ScenarioResult(
            scenario=Scenario(
                id="s2", name="Cascade failure from app",
                description="Cascade failure starting from app server",
                faults=[], traffic_multiplier=1.0,
            ),
            cascade=CascadeChain(trigger="Cascade: app", total_components=3),
            risk_score=5.0,
        ),
        ScenarioResult(
            scenario=Scenario(
                id="s3", name="Traffic spike 2x",
                description="Double traffic load scenario",
                faults=[], traffic_multiplier=2.0,
            ),
            cascade=CascadeChain(trigger="Traffic spike", total_components=3),
            risk_score=2.0,
        ),
    ]
    return SimulationReport(
        results=results,
        resilience_score=65.0,
        total_generated=3,
        was_truncated=False,
    )


# ===========================================================================
# CIGateConfig tests
# ===========================================================================


class TestCIGateConfig:
    """Test CIGateConfig defaults and fields."""

    def test_default_values(self) -> None:
        config = CIGateConfig()
        assert config.min_resilience_score == 70
        assert config.max_critical_findings == 0
        assert config.max_spof_count == 0
        assert config.fail_on_regression is True
        assert config.infrastructure_file == "infrastructure.yaml"
        assert config.output_format == "json"
        assert config.notify_slack is False
        assert config.slack_webhook == ""

    def test_custom_values(self) -> None:
        config = CIGateConfig(
            min_resilience_score=80,
            max_critical_findings=2,
            infrastructure_file="custom.yaml",
            notify_slack=True,
            slack_webhook="https://hooks.slack.com/test",
        )
        assert config.min_resilience_score == 80
        assert config.max_critical_findings == 2
        assert config.infrastructure_file == "custom.yaml"
        assert config.notify_slack is True


# ===========================================================================
# CIGateGenerator tests
# ===========================================================================


class TestCIGateGeneratorGitHub:
    """Test GitHub Actions workflow generation."""

    def test_generates_valid_yaml(self) -> None:
        gen = CIGateGenerator()
        config = CIGateConfig()
        result = gen.generate_github_action(config)
        # Should parse as valid YAML
        parsed = yaml.safe_load(result)
        assert parsed is not None
        assert "name" in parsed
        assert parsed["name"] == "FaultRay Resilience Gate"

    def test_contains_required_jobs(self) -> None:
        gen = CIGateGenerator()
        config = CIGateConfig()
        result = gen.generate_github_action(config)
        parsed = yaml.safe_load(result)
        assert "jobs" in parsed
        assert "resilience-check" in parsed["jobs"]

    def test_job_has_required_steps(self) -> None:
        gen = CIGateGenerator()
        config = CIGateConfig()
        result = gen.generate_github_action(config)
        parsed = yaml.safe_load(result)
        job = parsed["jobs"]["resilience-check"]
        steps = job["steps"]

        # Should have checkout, setup-python, install, analysis, sarif, pr-comment, sarif-upload
        step_names = [s.get("name", s.get("uses", "")) for s in steps]
        assert any("checkout" in str(s).lower() for s in step_names)
        assert any("Install FaultRay" in str(s) for s in step_names)
        assert any("Resilience" in str(s) for s in step_names)

    def test_contains_trigger_paths(self) -> None:
        gen = CIGateGenerator()
        config = CIGateConfig()
        result = gen.generate_github_action(config)
        parsed = yaml.safe_load(result)
        pr_paths = parsed["on"]["pull_request"]["paths"]
        assert "**/*.yaml" in pr_paths
        assert "**/*.tf" in pr_paths

    def test_contains_env_variables(self) -> None:
        gen = CIGateGenerator()
        config = CIGateConfig(min_resilience_score=85)
        result = gen.generate_github_action(config)
        parsed = yaml.safe_load(result)
        assert "env" in parsed
        assert parsed["env"]["MIN_SCORE"] == "85"

    def test_slack_notification_included_when_enabled(self) -> None:
        gen = CIGateGenerator()
        config = CIGateConfig(notify_slack=True)
        result = gen.generate_github_action(config)
        parsed = yaml.safe_load(result)
        steps = parsed["jobs"]["resilience-check"]["steps"]
        step_names = [s.get("name", "") for s in steps]
        assert "Notify Slack" in step_names

    def test_slack_notification_excluded_when_disabled(self) -> None:
        gen = CIGateGenerator()
        config = CIGateConfig(notify_slack=False)
        result = gen.generate_github_action(config)
        parsed = yaml.safe_load(result)
        steps = parsed["jobs"]["resilience-check"]["steps"]
        step_names = [s.get("name", "") for s in steps]
        assert "Notify Slack" not in step_names

    def test_regression_check_included_when_enabled(self) -> None:
        gen = CIGateGenerator()
        config = CIGateConfig(fail_on_regression=True)
        result = gen.generate_github_action(config)
        parsed = yaml.safe_load(result)
        steps = parsed["jobs"]["resilience-check"]["steps"]
        step_names = [s.get("name", "") for s in steps]
        assert "Check for Regression" in step_names

    def test_regression_check_excluded_when_disabled(self) -> None:
        gen = CIGateGenerator()
        config = CIGateConfig(fail_on_regression=False)
        result = gen.generate_github_action(config)
        parsed = yaml.safe_load(result)
        steps = parsed["jobs"]["resilience-check"]["steps"]
        step_names = [s.get("name", "") for s in steps]
        assert "Check for Regression" not in step_names

    def test_permissions_set(self) -> None:
        gen = CIGateGenerator()
        config = CIGateConfig()
        result = gen.generate_github_action(config)
        parsed = yaml.safe_load(result)
        perms = parsed["jobs"]["resilience-check"]["permissions"]
        assert "pull-requests" in perms
        assert "security-events" in perms

    def test_workflow_dispatch_inputs(self) -> None:
        gen = CIGateGenerator()
        config = CIGateConfig(min_resilience_score=90)
        result = gen.generate_github_action(config)
        parsed = yaml.safe_load(result)
        dispatch = parsed["on"]["workflow_dispatch"]
        assert "inputs" in dispatch
        assert "min_score" in dispatch["inputs"]
        assert dispatch["inputs"]["min_score"]["default"] == "90"


class TestCIGateGeneratorGitLab:
    """Test GitLab CI configuration generation."""

    def test_generates_valid_yaml(self) -> None:
        gen = CIGateGenerator()
        config = CIGateConfig()
        result = gen.generate_gitlab_ci(config)
        parsed = yaml.safe_load(result)
        assert parsed is not None
        assert "resilience-gate" in parsed

    def test_contains_script_section(self) -> None:
        gen = CIGateGenerator()
        config = CIGateConfig()
        result = gen.generate_gitlab_ci(config)
        parsed = yaml.safe_load(result)
        job = parsed["resilience-gate"]
        assert "script" in job
        assert "before_script" in job

    def test_uses_correct_image(self) -> None:
        gen = CIGateGenerator()
        config = CIGateConfig()
        result = gen.generate_gitlab_ci(config)
        parsed = yaml.safe_load(result)
        assert parsed["resilience-gate"]["image"] == "python:3.12-slim"

    def test_has_artifacts(self) -> None:
        gen = CIGateGenerator()
        config = CIGateConfig()
        result = gen.generate_gitlab_ci(config)
        parsed = yaml.safe_load(result)
        assert "artifacts" in parsed["resilience-gate"]

    def test_threshold_in_script(self) -> None:
        gen = CIGateGenerator()
        config = CIGateConfig(min_resilience_score=75)
        result = gen.generate_gitlab_ci(config)
        assert "75" in result


class TestCIGateGeneratorJenkins:
    """Test Jenkins pipeline generation."""

    def test_generates_groovy_stage(self) -> None:
        gen = CIGateGenerator()
        config = CIGateConfig()
        result = gen.generate_jenkins(config)
        assert "stage('Resilience Gate')" in result
        assert "steps {" in result

    def test_contains_pip_install(self) -> None:
        gen = CIGateGenerator()
        config = CIGateConfig()
        result = gen.generate_jenkins(config)
        assert "pip install faultray" in result

    def test_contains_threshold_check(self) -> None:
        gen = CIGateGenerator()
        config = CIGateConfig(min_resilience_score=90)
        result = gen.generate_jenkins(config)
        assert "90" in result
        assert "error" in result

    def test_contains_archive_artifacts(self) -> None:
        gen = CIGateGenerator()
        config = CIGateConfig()
        result = gen.generate_jenkins(config)
        assert "archiveArtifacts" in result

    def test_uses_infra_file(self) -> None:
        gen = CIGateGenerator()
        config = CIGateConfig(infrastructure_file="my-infra.yaml")
        result = gen.generate_jenkins(config)
        assert "my-infra.yaml" in result


# ===========================================================================
# SARIF Exporter tests
# ===========================================================================


class TestRiskMapping:
    """Test risk score to SARIF level mappings."""

    def test_critical_risk_maps_to_error(self) -> None:
        assert _risk_to_sarif_level(9.0) == "error"
        assert _risk_to_sarif_level(7.0) == "error"
        assert _risk_to_sarif_level(8.5) == "error"

    def test_warning_risk_maps_to_warning(self) -> None:
        assert _risk_to_sarif_level(4.0) == "warning"
        assert _risk_to_sarif_level(6.9) == "warning"

    def test_low_risk_maps_to_note(self) -> None:
        assert _risk_to_sarif_level(3.9) == "note"
        assert _risk_to_sarif_level(0.0) == "note"

    def test_severity_labels(self) -> None:
        assert _risk_to_severity(9.5) == "critical"
        assert _risk_to_severity(7.5) == "high"
        assert _risk_to_severity(5.0) == "medium"
        assert _risk_to_severity(2.0) == "low"


class TestRemediationMapping:
    """Test remediation suggestion lookup."""

    def test_spof_remediation(self) -> None:
        result = _get_remediation("Single Point of Failure in database")
        assert "redundancy" in result.lower() or "replicas" in result.lower()

    def test_cascade_remediation(self) -> None:
        result = _get_remediation("Cascade failure from web server")
        assert "circuit breaker" in result.lower()

    def test_traffic_remediation(self) -> None:
        result = _get_remediation("Traffic spike 3x")
        assert "autoscaling" in result.lower() or "rate limiting" in result.lower()

    def test_unknown_returns_generic(self) -> None:
        result = _get_remediation("some unknown scenario")
        assert len(result) > 0


class TestExportSarif:
    """Test SARIF document generation from SimulationReport."""

    def test_valid_sarif_structure(self) -> None:
        graph = _simple_graph()
        report = _simple_report()
        sarif = export_sarif(report, graph)

        assert sarif["version"] == "2.1.0"
        assert "$schema" in sarif
        assert "runs" in sarif
        assert len(sarif["runs"]) == 1

    def test_tool_information(self) -> None:
        graph = _simple_graph()
        report = _simple_report()
        sarif = export_sarif(report, graph)
        tool = sarif["runs"][0]["tool"]["driver"]

        assert tool["name"] == "FaultRay"
        assert "version" in tool
        assert "informationUri" in tool

    def test_rules_from_findings(self) -> None:
        graph = _simple_graph()
        report = _simple_report()
        sarif = export_sarif(report, graph)
        rules = sarif["runs"][0]["tool"]["driver"]["rules"]

        # Should have 2 rules (1 critical + 1 warning; the passed one is excluded)
        assert len(rules) == 2

    def test_results_match_findings(self) -> None:
        graph = _simple_graph()
        report = _simple_report()
        sarif = export_sarif(report, graph)
        results = sarif["runs"][0]["results"]

        assert len(results) == 2
        # First result should be error (critical), second warning
        assert results[0]["level"] == "error"
        assert results[1]["level"] == "warning"

    def test_results_have_locations(self) -> None:
        graph = _simple_graph()
        report = _simple_report()
        sarif = export_sarif(report, graph, infrastructure_file="infra.yaml")
        results = sarif["runs"][0]["results"]

        for result in results:
            assert len(result["locations"]) > 0
            loc = result["locations"][0]
            assert loc["physicalLocation"]["artifactLocation"]["uri"] == "infra.yaml"

    def test_invocations_present(self) -> None:
        graph = _simple_graph()
        report = _simple_report()
        sarif = export_sarif(report, graph)
        invocations = sarif["runs"][0]["invocations"]

        assert len(invocations) == 1
        assert invocations[0]["executionSuccessful"] is True

    def test_properties_contain_metrics(self) -> None:
        graph = _simple_graph()
        report = _simple_report()
        sarif = export_sarif(report, graph)
        props = sarif["runs"][0]["properties"]

        assert "resilience_score" in props
        assert props["resilience_score"] == 65.0
        assert "critical_count" in props
        assert "warning_count" in props

    def test_empty_report_produces_valid_sarif(self) -> None:
        graph = _simple_graph()
        report = SimulationReport(
            results=[],
            resilience_score=100.0,
            total_generated=0,
        )
        sarif = export_sarif(report, graph)

        assert sarif["version"] == "2.1.0"
        assert len(sarif["runs"][0]["results"]) == 0
        assert len(sarif["runs"][0]["tool"]["driver"]["rules"]) == 0

    def test_sarif_json_serializable(self) -> None:
        graph = _simple_graph()
        report = _simple_report()
        sarif = export_sarif(report, graph)
        # Should serialize without error
        json_str = json.dumps(sarif, indent=2)
        assert len(json_str) > 0
        # Should round-trip
        parsed = json.loads(json_str)
        assert parsed["version"] == "2.1.0"


class TestSARIFExporterFromJSON:
    """Test SARIF generation from JSON results (CI/CD pipeline mode)."""

    def test_from_json_with_scenarios(self) -> None:
        results = {
            "resilience_score": 70.0,
            "critical": 1,
            "warning": 2,
            "passed": 5,
            "scenarios": [
                {"name": "SPOF: db", "severity": "critical"},
                {"name": "Cascade: app", "severity": "warning"},
                {"name": "Traffic spike", "severity": "warning"},
                {"name": "Normal operation", "severity": "info"},
            ],
        }
        sarif = SARIFExporter.from_json_results(results)

        assert sarif["version"] == "2.1.0"
        # Should have 3 results (critical + 2 warnings, excluding info)
        assert len(sarif["runs"][0]["results"]) == 3

    def test_from_json_without_scenarios(self) -> None:
        results = {
            "resilience_score": 50.0,
            "critical": 2,
            "warning": 3,
            "passed": 10,
        }
        sarif = SARIFExporter.from_json_results(results)

        assert sarif["version"] == "2.1.0"
        # Should have 2 summary results (critical + warning)
        assert len(sarif["runs"][0]["results"]) == 2

    def test_from_json_all_passed(self) -> None:
        results = {
            "resilience_score": 100.0,
            "critical": 0,
            "warning": 0,
            "passed": 20,
        }
        sarif = SARIFExporter.from_json_results(results)

        assert len(sarif["runs"][0]["results"]) == 0

    def test_from_json_properties(self) -> None:
        results = {
            "resilience_score": 85.0,
            "critical": 0,
            "warning": 1,
            "passed": 15,
        }
        sarif = SARIFExporter.from_json_results(results)
        props = sarif["runs"][0]["properties"]

        assert props["resilience_score"] == 85.0
        assert props["critical_count"] == 0
        assert props["warning_count"] == 1

    def test_from_simulation_method(self) -> None:
        graph = _simple_graph()
        report = _simple_report()
        sarif = SARIFExporter.from_simulation(report, graph, "test.yaml")

        assert sarif["version"] == "2.1.0"
        assert len(sarif["runs"][0]["results"]) == 2
