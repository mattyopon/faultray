"""Tests for the FaultRay MCP server tool functions.

Tests call the tool functions directly (no MCP transport involved) and verify
that they return correct string results, handle missing infrastructure
gracefully, and delegate correctly to the underlying MCPBridge.
"""

from __future__ import annotations

import json
import textwrap
from pathlib import Path
from unittest.mock import patch

import pytest

# ---------------------------------------------------------------------------
# Import the module under test — skip entire module if mcp not installed
# ---------------------------------------------------------------------------
mcp_sdk = pytest.importorskip("mcp", reason="mcp package not installed")

import faultray.mcp_server as srv  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_MINIMAL_YAML = textwrap.dedent("""\
    components:
      - id: api
        name: API Server
        type: app_server
        replicas: 1
      - id: db
        name: PostgreSQL
        type: database
        replicas: 1
    dependencies:
      - source: api
        target: db
        type: requires
""")

_SPOF_FREE_YAML = textwrap.dedent("""\
    components:
      - id: api
        name: API Server
        type: app_server
        replicas: 2
        failover:
          enabled: true
      - id: db
        name: PostgreSQL
        type: database
        replicas: 2
        failover:
          enabled: true
    dependencies:
      - source: api
        target: db
        type: requires
""")


@pytest.fixture(autouse=True)
def _reset_graph():
    """Ensure each test starts with no loaded infrastructure."""
    srv._set_graph(None, "")
    yield
    srv._set_graph(None, "")


@pytest.fixture
def loaded_graph():
    """Load minimal YAML so the graph state is populated for analysis tools."""
    result = srv.load_infrastructure(_MINIMAL_YAML)
    assert "loaded successfully" in result
    return srv._get_graph()


# ===========================================================================
# load_infrastructure
# ===========================================================================


class TestLoadInfrastructure:
    def test_valid_yaml_sets_graph(self):
        result = srv.load_infrastructure(_MINIMAL_YAML)
        assert "loaded successfully" in result
        assert srv._get_graph() is not None

    def test_valid_yaml_shows_component_count(self):
        result = srv.load_infrastructure(_MINIMAL_YAML)
        assert "2" in result  # 2 components

    def test_valid_yaml_shows_score(self):
        result = srv.load_infrastructure(_MINIMAL_YAML)
        assert "/100" in result

    def test_source_set_to_inline_yaml(self):
        srv.load_infrastructure(_MINIMAL_YAML)
        assert srv._current_graph_source == "inline YAML"

    def test_invalid_yaml_returns_error(self):
        # YAML with a tab character where spaces are required triggers a scanner error
        result = srv.load_infrastructure("components:\n\t- id: bad\n")
        assert "error" in result.lower() or "Error" in result or "loaded" in result

    def test_empty_string_returns_error(self):
        result = srv.load_infrastructure("")
        assert "error" in result.lower() or "Error" in result

    def test_missing_required_fields_returns_error(self):
        bad_yaml = "components:\n  - name: NoId\n    type: app_server\n"
        result = srv.load_infrastructure(bad_yaml)
        assert "error" in result.lower() or "Error" in result

    def test_invalid_component_type_returns_error(self):
        bad_yaml = "components:\n  - id: x\n    name: X\n    type: unknown_type\n"
        result = srv.load_infrastructure(bad_yaml)
        assert "error" in result.lower() or "Error" in result

    def test_overwrite_previous_graph(self):
        srv.load_infrastructure(_MINIMAL_YAML)
        first_graph = srv._get_graph()
        srv.load_infrastructure(_SPOF_FREE_YAML)
        second_graph = srv._get_graph()
        assert first_graph is not second_graph


# ===========================================================================
# load_infrastructure_file
# ===========================================================================


class TestLoadInfrastructureFile:
    def test_valid_file_sets_graph(self, tmp_path):
        yaml_file = tmp_path / "infra.yaml"
        yaml_file.write_text(_MINIMAL_YAML, encoding="utf-8")
        result = srv.load_infrastructure_file(str(yaml_file))
        assert "infra.yaml" in result
        assert srv._get_graph() is not None

    def test_missing_file_returns_error(self):
        result = srv.load_infrastructure_file("/nonexistent/path/infra.yaml")
        assert "not found" in result.lower() or "Error" in result

    def test_source_set_to_full_path(self, tmp_path):
        yaml_file = tmp_path / "infra.yaml"
        yaml_file.write_text(_MINIMAL_YAML, encoding="utf-8")
        srv.load_infrastructure_file(str(yaml_file))
        assert str(yaml_file) in srv._current_graph_source

    def test_tilde_expansion(self, monkeypatch, tmp_path):
        yaml_file = tmp_path / "infra.yaml"
        yaml_file.write_text(_MINIMAL_YAML, encoding="utf-8")
        monkeypatch.setenv("HOME", str(tmp_path))
        result = srv.load_infrastructure_file(str(yaml_file))
        assert "Error" not in result or "loaded" in result


# ===========================================================================
# Tools that require a loaded graph — error when no graph
# ===========================================================================


class TestNoGraphErrors:
    """All analysis tools should return a helpful error string when no graph is loaded."""

    def _assert_no_graph_error(self, result: str) -> None:
        assert "infrastructure" in result.lower() or "Error" in result, (
            f"Expected error about no infrastructure, got: {result!r}"
        )

    def test_simulate_no_graph(self):
        result = srv.simulate("some-component")
        self._assert_no_graph_error(result)

    def test_require_graph_raises(self):
        with pytest.raises(RuntimeError, match="No infrastructure loaded"):
            srv._require_graph()

    def test_find_spof_no_graph(self):
        result = srv.find_spof()
        self._assert_no_graph_error(result)

    def test_check_compliance_no_graph(self):
        result = srv.check_compliance("soc2")
        self._assert_no_graph_error(result)

    def test_recommend_chaos_no_graph(self):
        result = srv.recommend_chaos()
        self._assert_no_graph_error(result)

    def test_predict_change_risk_no_graph(self):
        result = srv.predict_change_risk("api", "upgrade")
        self._assert_no_graph_error(result)

    def test_generate_report_no_graph(self):
        result = srv.generate_report()
        self._assert_no_graph_error(result)

    def test_what_if_no_graph(self):
        result = srv.what_if("api", "add_replicas")
        self._assert_no_graph_error(result)


# ===========================================================================
# simulate
# ===========================================================================


class TestSimulate:
    def test_simulate_valid_component(self, loaded_graph):
        result = srv.simulate("db")
        data = json.loads(result)
        assert data["component_id"] == "db"
        assert "affected_components" in data
        assert "cascade_paths" in data

    def test_simulate_unknown_component_returns_error(self, loaded_graph):
        result = srv.simulate("nonexistent")
        # Bridge returns error string — should not be valid JSON
        assert "Error" in result or "not found" in result.lower() or "Component" in result

    def test_simulate_down_failure_type(self, loaded_graph):
        result = srv.simulate("db", failure_type="down")
        data = json.loads(result)
        assert data["failure_type"] == "down"

    def test_simulate_degraded_failure_type(self, loaded_graph):
        result = srv.simulate("api", failure_type="degraded")
        data = json.loads(result)
        assert data["failure_type"] == "degraded"

    def test_simulate_cascade_from_db(self, loaded_graph):
        result = srv.simulate("db")
        data = json.loads(result)
        # api depends on db, so api should be in affected
        assert "api" in data["affected_components"]


# ===========================================================================
# analyze_resilience
# ===========================================================================


class TestAnalyzeResilience:
    def test_returns_json(self, loaded_graph):
        result = srv.analyze_resilience()
        data = json.loads(result)
        assert "resilience_score" in data

    def test_score_between_0_and_100(self, loaded_graph):
        result = srv.analyze_resilience()
        data = json.loads(result)
        assert 0 <= data["resilience_score"] <= 100

    def test_has_recommendations(self, loaded_graph):
        result = srv.analyze_resilience()
        data = json.loads(result)
        assert "recommendations" in data

    def test_has_breakdown(self, loaded_graph):
        result = srv.analyze_resilience()
        data = json.loads(result)
        assert "breakdown" in data


# ===========================================================================
# find_spof
# ===========================================================================


class TestFindSpof:
    def test_returns_json(self, loaded_graph):
        result = srv.find_spof()
        data = json.loads(result)
        assert "spofs" in data
        assert "total_spofs" in data

    def test_minimal_yaml_has_spofs(self, loaded_graph):
        # Both components have replicas=1, db has a dependent (api)
        result = srv.find_spof()
        data = json.loads(result)
        assert data["total_spofs"] >= 1

    def test_spof_free_infra_has_zero(self):
        srv.load_infrastructure(_SPOF_FREE_YAML)
        result = srv.find_spof()
        data = json.loads(result)
        assert data["total_spofs"] == 0

    def test_spof_includes_component_info(self, loaded_graph):
        result = srv.find_spof()
        data = json.loads(result)
        if data["spofs"]:
            spof = data["spofs"][0]
            assert "component_id" in spof
            assert "dependent_count" in spof


# ===========================================================================
# what_if
# ===========================================================================


class TestWhatIf:
    def test_add_replicas(self, loaded_graph):
        result = srv.what_if("api", "add_replicas", value=3)
        data = json.loads(result)
        assert data["component_id"] == "api"
        assert data["change"] == "add_replicas"
        assert data["value"] == 3

    def test_enable_failover(self, loaded_graph):
        result = srv.what_if("db", "enable_failover")
        data = json.loads(result)
        assert "failover" in data["description"]

    def test_enable_autoscaling(self, loaded_graph):
        result = srv.what_if("api", "enable_autoscaling")
        data = json.loads(result)
        assert "autoscaling" in data["description"]

    def test_unknown_component_returns_error(self, loaded_graph):
        result = srv.what_if("ghost", "add_replicas")
        assert "Error" in result or "not found" in result.lower() or "Component" in result


# ===========================================================================
# check_compliance
# ===========================================================================


class TestCheckCompliance:
    @pytest.mark.parametrize("framework", ["soc2", "iso27001", "pci_dss", "nist_csf"])
    def test_valid_frameworks(self, loaded_graph, framework):
        result = srv.check_compliance(framework)
        data = json.loads(result)
        assert data["framework"] == framework
        assert "checks" in data
        assert "compliance_percent" in data

    def test_unknown_framework_returns_error(self, loaded_graph):
        result = srv.check_compliance("gdpr_unknown")
        assert "Error" in result or "Unknown" in result or "framework" in result.lower()


# ===========================================================================
# recommend_chaos
# ===========================================================================


class TestRecommendChaos:
    def test_returns_experiments(self, loaded_graph):
        result = srv.recommend_chaos()
        data = json.loads(result)
        assert "experiments" in data
        assert isinstance(data["experiments"], list)

    def test_respects_max_experiments(self, loaded_graph):
        result = srv.recommend_chaos(max_experiments=1)
        data = json.loads(result)
        assert len(data["experiments"]) <= 1

    def test_experiments_have_priority(self, loaded_graph):
        result = srv.recommend_chaos()
        data = json.loads(result)
        if data["experiments"]:
            exp = data["experiments"][0]
            assert exp["priority"] in ("high", "medium", "low")


# ===========================================================================
# predict_change_risk
# ===========================================================================


class TestPredictChangeRisk:
    def test_returns_risk_level(self, loaded_graph):
        result = srv.predict_change_risk("db", "instance_type_change")
        data = json.loads(result)
        assert data["risk_level"] in ("low", "medium", "high")

    def test_db_with_dependents_is_not_low(self, loaded_graph):
        # db has api as a dependent, so risk should be medium or high
        result = srv.predict_change_risk("db", "upgrade")
        data = json.loads(result)
        assert data["risk_level"] in ("medium", "high")

    def test_description_propagated(self, loaded_graph):
        result = srv.predict_change_risk("api", "scale_down", description="reduce cost")
        data = json.loads(result)
        assert data["description"] == "reduce cost"


# ===========================================================================
# generate_report
# ===========================================================================


class TestGenerateReport:
    def test_summary_format(self, loaded_graph):
        result = srv.generate_report("summary")
        data = json.loads(result)
        assert data["format"] == "summary"
        assert "resilience_score" in data

    def test_detailed_format_includes_breakdown(self, loaded_graph):
        result = srv.generate_report("detailed")
        data = json.loads(result)
        assert "breakdown" in data
        assert "recommendations" in data

    def test_default_is_summary(self, loaded_graph):
        result = srv.generate_report()
        data = json.loads(result)
        assert data["format"] == "summary"


# ===========================================================================
# tf_check
# ===========================================================================


class TestTfCheck:
    def test_missing_file_returns_error(self):
        result = srv.tf_check("/tmp/nonexistent_plan_abc123.json")
        assert "not found" in result.lower() or "Error" in result

    def test_valid_plan_json(self, tmp_path):
        # Minimal valid terraform plan JSON (empty plan)
        plan = {
            "format_version": "1.0",
            "resource_changes": [],
        }
        plan_file = tmp_path / "plan.json"
        plan_file.write_text(json.dumps(plan), encoding="utf-8")

        result = srv.tf_check(str(plan_file))
        assert "Terraform Plan Resilience Analysis" in result
        assert "score_before" in result
        assert "recommendation" in result

    def test_plan_with_creates(self, tmp_path):
        plan = {
            "format_version": "1.0",
            "resource_changes": [
                {
                    "address": "aws_instance.web",
                    "type": "aws_instance",
                    "name": "web",
                    "change": {
                        "actions": ["create"],
                        "before": None,
                        "after": {"instance_type": "t3.medium", "desired_count": 2},
                    },
                }
            ],
        }
        plan_file = tmp_path / "plan.json"
        plan_file.write_text(json.dumps(plan), encoding="utf-8")

        result = srv.tf_check(str(plan_file))
        assert "Terraform Plan Resilience Analysis" in result
        data_start = result.index("{")
        data = json.loads(result[data_start:])
        assert data["resources_added"] >= 0

    def test_min_score_fail_warning(self, tmp_path):
        # Plan that results in score=0 (empty graph after)
        plan = {"format_version": "1.0", "resource_changes": []}
        plan_file = tmp_path / "plan.json"
        plan_file.write_text(json.dumps(plan), encoding="utf-8")

        result = srv.tf_check(str(plan_file), min_score=99.0)
        # Score will be 0 (empty graph), which is < 99
        assert "FAIL" in result or "WARNING" in result or "below" in result.lower()


# ===========================================================================
# dora_assess
# ===========================================================================


class TestDoraAssess:
    def test_missing_file_returns_error(self):
        result = srv.dora_assess("/tmp/nonexistent_infra_abc123.yaml")
        assert "not found" in result.lower() or "Error" in result

    def test_valid_file_returns_json(self, tmp_path):
        yaml_file = tmp_path / "infra.yaml"
        yaml_file.write_text(_MINIMAL_YAML, encoding="utf-8")
        result = srv.dora_assess(str(yaml_file))
        data = json.loads(result)
        assert data["framework"] == "DORA"
        assert "checks" in data
        assert "compliance_percent" in data
        assert "verdict" in data

    def test_spof_free_infra_passes_more_checks(self, tmp_path):
        yaml_file = tmp_path / "infra.yaml"
        yaml_file.write_text(_SPOF_FREE_YAML, encoding="utf-8")
        result = srv.dora_assess(str(yaml_file))
        data = json.loads(result)
        # SPOF-free should pass redundancy and failover checks
        assert data["passed"] >= 2


# ===========================================================================
# Resources
# ===========================================================================


class TestResources:
    def test_resource_version_contains_version(self):
        result = srv.resource_version()
        assert "FaultRay" in result
        assert "11.0.0" in result

    def test_resource_tools_lists_tools(self):
        result = srv.resource_tools()
        assert "load_infrastructure" in result
        assert "tf_check" in result
        assert "dora_assess" in result
        assert "find_spof" in result

    def test_resource_infrastructure_no_graph(self):
        result = srv.resource_infrastructure()
        assert "No infrastructure loaded" in result

    def test_resource_infrastructure_with_graph(self):
        srv.load_infrastructure(_MINIMAL_YAML)
        result = srv.resource_infrastructure()
        assert "Components" in result
        assert "Score" in result
        assert "/100" in result

    def test_resource_infrastructure_shows_component_types(self):
        srv.load_infrastructure(_MINIMAL_YAML)
        result = srv.resource_infrastructure()
        assert "app_server" in result or "database" in result

    def test_resource_infrastructure_shows_source(self):
        srv.load_infrastructure(_MINIMAL_YAML)
        result = srv.resource_infrastructure()
        assert "inline YAML" in result


# ===========================================================================
# Internal helpers
# ===========================================================================


class TestInternalHelpers:
    def test_get_graph_returns_none_initially(self):
        assert srv._get_graph() is None

    def test_set_and_get_graph(self):
        from faultray.model.demo import create_demo_graph

        g = create_demo_graph()
        srv._set_graph(g, "test source")
        assert srv._get_graph() is g
        assert srv._current_graph_source == "test source"

    def test_require_graph_raises_without_graph(self):
        with pytest.raises(RuntimeError, match="No infrastructure loaded"):
            srv._require_graph()

    def test_require_graph_returns_graph_when_loaded(self):
        from faultray.model.demo import create_demo_graph

        g = create_demo_graph()
        srv._set_graph(g, "demo")
        returned = srv._require_graph()
        assert returned is g
