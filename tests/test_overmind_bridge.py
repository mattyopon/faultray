"""Tests for the Overmind x FaultRay bridge integration."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from faultray.integrations.overmind_bridge import (
    EnrichedAnalysis,
    OvermindAnalysis,
    OvermindBridge,
    OvermindBlastRadius,
    OvermindChange,
    OvermindRisk,
    _normalize_severity,
)
from faultray.model.components import Component, ComponentType, Dependency
from faultray.model.graph import InfraGraph
from faultray.simulator.scenarios import FaultType


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def _make_graph_with_components() -> InfraGraph:
    """Build a small InfraGraph for testing."""
    graph = InfraGraph()

    lb = Component(
        id="lb-1",
        name="load_balancer",
        type=ComponentType.LOAD_BALANCER,
        replicas=2,
    )
    web = Component(
        id="web-1",
        name="web",
        type=ComponentType.WEB_SERVER,
        replicas=2,
    )
    db = Component(
        id="db-1",
        name="database",
        type=ComponentType.DATABASE,
        replicas=1,
    )

    graph.add_component(lb)
    graph.add_component(web)
    graph.add_component(db)

    graph.add_dependency(Dependency(source_id="web-1", target_id="lb-1"))
    graph.add_dependency(Dependency(source_id="web-1", target_id="db-1"))

    return graph


def _make_overmind_json(
    *,
    risks: list[dict] | None = None,
    changes: list[dict] | None = None,
    metadata: dict | None = None,
) -> dict:
    """Build a minimal Overmind JSON dict."""
    return {
        "metadata": metadata or {"run_id": "test-run-001", "plan_file": "main.tf"},
        "risks": risks or [],
        "changes": changes or [],
    }


def _make_risk(
    uuid: str = "risk-1",
    severity: str = "high",
    title: str = "Risk title",
    description: str = "Risk description",
) -> dict:
    return {
        "uuid": uuid,
        "severity": severity,
        "title": title,
        "description": description,
    }


def _make_change(
    resource_type: str = "aws_instance",
    resource_address: str = "aws_instance.web",
    action: str = "update",
    directly_affected: list[str] | None = None,
    indirectly_affected: list[str] | None = None,
) -> dict:
    return {
        "resource_type": resource_type,
        "resource_address": resource_address,
        "action": action,
        "blast_radius": {
            "directly_affected": directly_affected or [],
            "indirectly_affected": indirectly_affected or [],
        },
    }


# ---------------------------------------------------------------------------
# _normalize_severity
# ---------------------------------------------------------------------------


class TestNormalizeSeverity:
    def test_known_severities(self):
        for sev in ("critical", "high", "medium", "low", "info"):
            assert _normalize_severity(sev) == sev

    def test_uppercase_input(self):
        assert _normalize_severity("CRITICAL") == "critical"
        assert _normalize_severity("HIGH") == "high"

    def test_unknown_defaults_to_medium(self):
        assert _normalize_severity("unknown_level") == "medium"
        assert _normalize_severity("") == "medium"
        assert _normalize_severity(None) == "medium"  # type: ignore[arg-type]

    def test_whitespace_stripped(self):
        assert _normalize_severity("  high  ") == "high"


# ---------------------------------------------------------------------------
# OvermindRisk
# ---------------------------------------------------------------------------


class TestOvermindRisk:
    def test_severity_score_critical(self):
        risk = OvermindRisk(uuid="r1", severity="critical", title="t", description="d")
        assert risk.severity_score == 9.0

    def test_severity_score_info(self):
        risk = OvermindRisk(uuid="r1", severity="info", title="t", description="d")
        assert risk.severity_score == 0.5

    def test_severity_rank_ordering(self):
        critical = OvermindRisk(uuid="r1", severity="critical", title="t", description="d")
        low = OvermindRisk(uuid="r2", severity="low", title="t", description="d")
        assert critical.severity_rank > low.severity_rank


# ---------------------------------------------------------------------------
# OvermindBlastRadius
# ---------------------------------------------------------------------------


class TestOvermindBlastRadius:
    def test_all_affected_deduplicates(self):
        br = OvermindBlastRadius(
            directly_affected=["a", "b"],
            indirectly_affected=["b", "c"],
        )
        assert br.all_affected == ["a", "b", "c"]

    def test_affected_count(self):
        br = OvermindBlastRadius(
            directly_affected=["a", "b"],
            indirectly_affected=["c"],
        )
        assert br.affected_count == 3

    def test_empty_blast_radius(self):
        br = OvermindBlastRadius()
        assert br.all_affected == []
        assert br.affected_count == 0


# ---------------------------------------------------------------------------
# OvermindChange
# ---------------------------------------------------------------------------


class TestOvermindChange:
    def test_is_destructive_for_delete(self):
        change = OvermindChange(
            resource_type="aws_instance", resource_address="aws_instance.web",
            action="delete",
        )
        assert change.is_destructive is True

    def test_is_destructive_for_replace(self):
        change = OvermindChange(
            resource_type="aws_instance", resource_address="aws_instance.web",
            action="replace",
        )
        assert change.is_destructive is True

    def test_not_destructive_for_update(self):
        change = OvermindChange(
            resource_type="aws_instance", resource_address="aws_instance.web",
            action="update",
        )
        assert change.is_destructive is False

    def test_not_destructive_for_create(self):
        change = OvermindChange(
            resource_type="aws_instance", resource_address="aws_instance.web",
            action="create",
        )
        assert change.is_destructive is False


# ---------------------------------------------------------------------------
# OvermindBridge.from_overmind_json  (parsing)
# ---------------------------------------------------------------------------


class TestFromOvermindJson:
    def test_empty_json(self):
        analysis = OvermindBridge.from_overmind_json({})
        assert isinstance(analysis, OvermindAnalysis)
        assert analysis.risks == []
        assert analysis.changes == []
        assert analysis.metadata == {}

    def test_parses_risks(self):
        data = _make_overmind_json(risks=[
            _make_risk("r1", "critical", "Critical issue", "Something broke"),
            _make_risk("r2", "low", "Low issue", "Minor"),
        ])
        analysis = OvermindBridge.from_overmind_json(data)

        assert len(analysis.risks) == 2
        assert analysis.risks[0].uuid == "r1"
        assert analysis.risks[0].severity == "critical"
        assert analysis.risks[0].title == "Critical issue"
        assert analysis.risks[1].severity == "low"

    def test_parses_changes(self):
        data = _make_overmind_json(changes=[
            _make_change(
                "aws_instance", "aws_instance.web", "update",
                directly_affected=["aws_instance.web"],
                indirectly_affected=["aws_rds.db"],
            )
        ])
        analysis = OvermindBridge.from_overmind_json(data)

        assert len(analysis.changes) == 1
        change = analysis.changes[0]
        assert change.resource_type == "aws_instance"
        assert change.resource_address == "aws_instance.web"
        assert change.action == "update"
        assert "aws_instance.web" in change.blast_radius.directly_affected
        assert "aws_rds.db" in change.blast_radius.indirectly_affected

    def test_parses_metadata(self):
        data = _make_overmind_json(metadata={"run_id": "abc123", "plan_file": "main.tf"})
        analysis = OvermindBridge.from_overmind_json(data)
        assert analysis.metadata["run_id"] == "abc123"

    def test_handles_missing_blast_radius(self):
        """Changes without blast_radius field should parse without error."""
        data = {
            "changes": [{
                "resource_type": "aws_s3_bucket",
                "resource_address": "aws_s3_bucket.logs",
                "action": "create",
            }]
        }
        analysis = OvermindBridge.from_overmind_json(data)
        assert len(analysis.changes) == 1
        assert analysis.changes[0].blast_radius.affected_count == 0

    def test_handles_alternative_field_names(self):
        """Supports alternative field names used by different Overmind versions."""
        data = {
            "risks": [{"id": "r1", "severity": "HIGH", "name": "Risk A", "detail": "Detail A"}],
            "changes": [{
                "type": "aws_db_instance",
                "address": "aws_db_instance.main",
                "change_type": "DELETE",
                "affected": ["aws_db_instance.main"],
            }],
        }
        analysis = OvermindBridge.from_overmind_json(data)
        assert len(analysis.risks) == 1
        assert analysis.risks[0].title == "Risk A"
        assert analysis.risks[0].severity == "high"

        assert len(analysis.changes) == 1
        assert analysis.changes[0].action == "delete"
        assert analysis.changes[0].blast_radius.directly_affected == ["aws_db_instance.main"]

    def test_invalid_risk_entries_skipped(self):
        """Non-dict entries in the risks list should be silently skipped."""
        data = {"risks": [None, "not-a-dict", {"uuid": "r1", "severity": "low", "title": "ok", "description": ""}]}
        analysis = OvermindBridge.from_overmind_json(data)
        assert len(analysis.risks) == 1

    def test_highest_risk_severity(self):
        data = _make_overmind_json(risks=[
            _make_risk("r1", "low", "Low"),
            _make_risk("r2", "critical", "Critical"),
            _make_risk("r3", "medium", "Medium"),
        ])
        analysis = OvermindBridge.from_overmind_json(data)
        assert analysis.highest_risk_severity == "critical"

    def test_all_blast_radius_items_deduped(self):
        data = _make_overmind_json(changes=[
            _make_change(directly_affected=["res_a", "res_b"], indirectly_affected=["res_c"]),
            _make_change(
                resource_address="aws_instance.app", action="create",
                directly_affected=["res_b", "res_d"],
            ),
        ])
        analysis = OvermindBridge.from_overmind_json(data)
        items = analysis.all_blast_radius_items
        # res_b appears in both changes but should appear only once
        assert items.count("res_b") == 1
        assert set(items) == {"res_a", "res_b", "res_c", "res_d"}


# ---------------------------------------------------------------------------
# OvermindBridge._resolve_resource
# ---------------------------------------------------------------------------


class TestResolveResource:
    def test_exact_id_match(self):
        graph = _make_graph_with_components()
        result = OvermindBridge._resolve_resource("lb-1", graph)
        assert result == "lb-1"

    def test_exact_name_match(self):
        graph = _make_graph_with_components()
        result = OvermindBridge._resolve_resource("web", graph)
        assert result == "web-1"

    def test_suffix_match(self):
        """'aws_instance.web' suffix 'web' should resolve to 'web-1'."""
        graph = _make_graph_with_components()
        result = OvermindBridge._resolve_resource("aws_instance.web", graph)
        assert result == "web-1"

    def test_suffix_match_database(self):
        graph = _make_graph_with_components()
        result = OvermindBridge._resolve_resource("aws_db_instance.database", graph)
        assert result == "db-1"

    def test_case_insensitive_suffix(self):
        graph = _make_graph_with_components()
        result = OvermindBridge._resolve_resource("aws_instance.WEB", graph)
        assert result == "web-1"

    def test_no_match_returns_none(self):
        graph = _make_graph_with_components()
        result = OvermindBridge._resolve_resource("aws_instance.nonexistent_xyz", graph)
        assert result is None

    def test_empty_address_returns_none(self):
        graph = _make_graph_with_components()
        assert OvermindBridge._resolve_resource("", graph) is None

    def test_empty_graph_returns_none(self):
        graph = InfraGraph()
        result = OvermindBridge._resolve_resource("aws_instance.web", graph)
        assert result is None


# ---------------------------------------------------------------------------
# OvermindBridge._action_to_fault_type
# ---------------------------------------------------------------------------


class TestActionToFaultType:
    def test_delete_maps_to_component_down(self):
        assert OvermindBridge._action_to_fault_type("delete") == FaultType.COMPONENT_DOWN

    def test_replace_maps_to_component_down(self):
        assert OvermindBridge._action_to_fault_type("replace") == FaultType.COMPONENT_DOWN

    def test_update_maps_to_latency_spike(self):
        assert OvermindBridge._action_to_fault_type("update") == FaultType.LATENCY_SPIKE

    def test_create_maps_to_latency_spike(self):
        assert OvermindBridge._action_to_fault_type("create") == FaultType.LATENCY_SPIKE

    def test_unknown_action_defaults_to_component_down(self):
        assert OvermindBridge._action_to_fault_type("reboot") == FaultType.COMPONENT_DOWN

    def test_case_insensitive(self):
        assert OvermindBridge._action_to_fault_type("DELETE") == FaultType.COMPONENT_DOWN
        assert OvermindBridge._action_to_fault_type("UPDATE") == FaultType.LATENCY_SPIKE


# ---------------------------------------------------------------------------
# OvermindBridge.enrich_with_cascade
# ---------------------------------------------------------------------------


class TestEnrichWithCascade:
    def test_returns_enriched_analysis(self):
        graph = _make_graph_with_components()
        bridge = OvermindBridge(graph=graph)

        data = _make_overmind_json(changes=[
            _make_change(
                "aws_instance", "aws_instance.web", "update",
                directly_affected=["aws_instance.web"],
            )
        ])
        analysis = OvermindBridge.from_overmind_json(data)
        enriched = bridge.enrich_with_cascade(analysis, graph)

        assert isinstance(enriched, EnrichedAnalysis)
        assert enriched.overmind is analysis

    def test_matched_resource_creates_cascade_impact(self):
        graph = _make_graph_with_components()
        bridge = OvermindBridge(graph=graph)

        data = _make_overmind_json(changes=[
            _make_change(
                "aws_instance", "aws_instance.web", "delete",
                directly_affected=["aws_instance.web"],
            )
        ])
        analysis = OvermindBridge.from_overmind_json(data)
        enriched = bridge.enrich_with_cascade(analysis, graph)

        # 'web' resolves to 'web-1' via suffix match
        assert len(enriched.cascade_impacts) == 1
        impact = enriched.cascade_impacts[0]
        assert impact.component_id == "web-1"
        assert impact.component_name == "web"
        assert impact.triggered_by == "aws_instance.web"

    def test_unresolvable_resource_goes_to_unmapped(self):
        graph = _make_graph_with_components()
        bridge = OvermindBridge(graph=graph)

        data = _make_overmind_json(changes=[
            _make_change(
                "aws_lambda_function", "aws_lambda_function.nonexistent_xyz", "update",
                directly_affected=["aws_lambda_function.nonexistent_xyz"],
            )
        ])
        analysis = OvermindBridge.from_overmind_json(data)
        enriched = bridge.enrich_with_cascade(analysis, graph)

        assert len(enriched.cascade_impacts) == 0
        assert "aws_lambda_function.nonexistent_xyz" in enriched.unmapped_resources

    def test_empty_analysis_empty_enrichment(self):
        graph = _make_graph_with_components()
        bridge = OvermindBridge(graph=graph)

        analysis = OvermindBridge.from_overmind_json({})
        enriched = bridge.enrich_with_cascade(analysis, graph)

        assert enriched.cascade_impacts == []
        assert enriched.unmapped_resources == []

    def test_empty_graph_all_unmapped(self):
        graph = InfraGraph()
        bridge = OvermindBridge(graph=graph)

        data = _make_overmind_json(changes=[
            _make_change(directly_affected=["aws_instance.web", "aws_rds.db"])
        ])
        analysis = OvermindBridge.from_overmind_json(data)
        enriched = bridge.enrich_with_cascade(analysis, graph)

        assert len(enriched.cascade_impacts) == 0
        assert len(enriched.unmapped_resources) == 2

    def test_cascade_impact_has_severity(self):
        """cascade_severity should be >= 0."""
        graph = _make_graph_with_components()
        bridge = OvermindBridge(graph=graph)

        data = _make_overmind_json(changes=[
            _make_change(
                "aws_db_instance", "aws_db_instance.database", "delete",
                directly_affected=["aws_db_instance.database"],
            )
        ])
        analysis = OvermindBridge.from_overmind_json(data)
        enriched = bridge.enrich_with_cascade(analysis, graph)

        # database resolves to db-1
        impacts = [i for i in enriched.cascade_impacts if i.component_id == "db-1"]
        assert len(impacts) >= 1
        assert impacts[0].overall_severity >= 0.0

    def test_uses_graph_from_constructor_when_no_graph_param(self):
        """enrich_with_cascade should fall back to self._graph."""
        graph = _make_graph_with_components()
        bridge = OvermindBridge(graph=graph)

        data = _make_overmind_json(changes=[
            _make_change(directly_affected=["aws_instance.web"])
        ])
        analysis = OvermindBridge.from_overmind_json(data)
        # Pass graph=None to force fallback to constructor graph
        enriched = bridge.enrich_with_cascade(analysis, None)

        assert len(enriched.cascade_impacts) == 1

    def test_total_cascade_affected_is_deduplicated(self):
        graph = _make_graph_with_components()
        bridge = OvermindBridge(graph=graph)

        data = _make_overmind_json(changes=[
            _make_change(
                directly_affected=["aws_instance.web"],
                indirectly_affected=["aws_instance.web"],  # duplicate
            )
        ])
        analysis = OvermindBridge.from_overmind_json(data)
        enriched = bridge.enrich_with_cascade(analysis, graph)

        # web-1 should appear only once
        total = enriched.total_cascade_affected
        assert total.count("web-1") == 1

    def test_generated_at_is_set(self):
        bridge = OvermindBridge()
        analysis = OvermindBridge.from_overmind_json({})
        enriched = bridge.enrich_with_cascade(analysis)
        assert enriched.generated_at != ""


# ---------------------------------------------------------------------------
# OvermindBridge.generate_combined_report
# ---------------------------------------------------------------------------


class TestGenerateCombinedReport:
    def test_report_structure(self):
        bridge = OvermindBridge()
        analysis = OvermindBridge.from_overmind_json({})
        enriched = bridge.enrich_with_cascade(analysis)
        report = bridge.generate_combined_report(enriched)

        assert "generated_at" in report
        assert "summary" in report
        assert "overmind" in report
        assert "cascade_analysis" in report
        assert "recommendations" in report

    def test_summary_counts(self):
        data = _make_overmind_json(
            risks=[_make_risk("r1", "critical"), _make_risk("r2", "low")],
            changes=[
                _make_change(
                    directly_affected=["res_a", "res_b"],
                    indirectly_affected=["res_c"],
                )
            ],
        )
        bridge = OvermindBridge()
        analysis = OvermindBridge.from_overmind_json(data)
        enriched = bridge.enrich_with_cascade(analysis)
        report = bridge.generate_combined_report(enriched)

        summary = report["summary"]
        assert summary["overmind_risks"] == 2
        assert summary["overmind_changes"] == 1
        assert summary["blast_radius_items"] == 3
        assert summary["highest_risk_severity"] == "critical"

    def test_risks_sorted_by_severity(self):
        data = _make_overmind_json(risks=[
            _make_risk("r1", "low", "Low Risk"),
            _make_risk("r2", "critical", "Critical Risk"),
            _make_risk("r3", "medium", "Medium Risk"),
        ])
        bridge = OvermindBridge()
        analysis = OvermindBridge.from_overmind_json(data)
        enriched = bridge.enrich_with_cascade(analysis)
        report = bridge.generate_combined_report(enriched)

        severities = [r["severity"] for r in report["overmind"]["risks"]]
        # Critical should come first
        assert severities[0] == "critical"

    def test_metadata_preserved(self):
        data = _make_overmind_json(metadata={"run_id": "my-run"})
        bridge = OvermindBridge()
        analysis = OvermindBridge.from_overmind_json(data)
        enriched = bridge.enrich_with_cascade(analysis)
        report = bridge.generate_combined_report(enriched)

        assert report["overmind"]["metadata"]["run_id"] == "my-run"

    def test_unmapped_resources_in_report(self):
        graph = InfraGraph()
        bridge = OvermindBridge(graph=graph)

        data = _make_overmind_json(changes=[
            _make_change(directly_affected=["aws_instance.unknown"])
        ])
        analysis = OvermindBridge.from_overmind_json(data)
        enriched = bridge.enrich_with_cascade(analysis, graph)
        report = bridge.generate_combined_report(enriched)

        assert "aws_instance.unknown" in report["cascade_analysis"]["unmapped_resources"]

    def test_cascade_impacts_in_report(self):
        graph = _make_graph_with_components()
        bridge = OvermindBridge(graph=graph)

        data = _make_overmind_json(changes=[
            _make_change(
                "aws_instance", "aws_instance.web", "delete",
                directly_affected=["aws_instance.web"],
            )
        ])
        analysis = OvermindBridge.from_overmind_json(data)
        enriched = bridge.enrich_with_cascade(analysis, graph)
        report = bridge.generate_combined_report(enriched)

        impacts = report["cascade_analysis"]["impacts"]
        assert len(impacts) >= 1
        impact = impacts[0]
        assert "component_id" in impact
        assert "component_name" in impact
        assert "triggered_by" in impact
        assert "cascade_severity" in impact
        assert isinstance(impact["cascade_severity"], float)

    def test_empty_report_has_safe_recommendation(self):
        bridge = OvermindBridge()
        analysis = OvermindBridge.from_overmind_json({})
        enriched = bridge.enrich_with_cascade(analysis)
        report = bridge.generate_combined_report(enriched)

        assert len(report["recommendations"]) >= 1
        # Should contain a "safe" message when nothing is wrong
        assert any("safe" in rec.lower() for rec in report["recommendations"])

    def test_destructive_change_triggers_recommendation(self):
        data = _make_overmind_json(changes=[
            _make_change(
                "aws_db_instance", "aws_db_instance.main", "delete",
                directly_affected=["aws_db_instance.main"],
            )
        ])
        bridge = OvermindBridge()
        analysis = OvermindBridge.from_overmind_json(data)
        enriched = bridge.enrich_with_cascade(analysis)
        report = bridge.generate_combined_report(enriched)

        recs_text = " ".join(report["recommendations"]).lower()
        assert "destructive" in recs_text

    def test_critical_risk_triggers_recommendation(self):
        data = _make_overmind_json(risks=[
            _make_risk("r1", "critical", "DB deletion will cause downtime"),
        ])
        bridge = OvermindBridge()
        analysis = OvermindBridge.from_overmind_json(data)
        enriched = bridge.enrich_with_cascade(analysis)
        report = bridge.generate_combined_report(enriched)

        recs_text = " ".join(report["recommendations"]).lower()
        assert "critical" in recs_text or "high" in recs_text or "risk" in recs_text

    def test_unmapped_resources_trigger_recommendation(self):
        graph = InfraGraph()
        bridge = OvermindBridge(graph=graph)

        data = _make_overmind_json(changes=[
            _make_change(directly_affected=["aws_lambda.missing"])
        ])
        analysis = OvermindBridge.from_overmind_json(data)
        enriched = bridge.enrich_with_cascade(analysis, graph)
        report = bridge.generate_combined_report(enriched)

        recs_text = " ".join(report["recommendations"]).lower()
        assert "unmapped" in recs_text or "map" in recs_text

    def test_large_blast_radius_triggers_recommendation(self):
        items = [f"aws_instance.resource_{i}" for i in range(12)]
        data = _make_overmind_json(changes=[
            _make_change(directly_affected=items)
        ])
        bridge = OvermindBridge()
        analysis = OvermindBridge.from_overmind_json(data)
        enriched = bridge.enrich_with_cascade(analysis)
        report = bridge.generate_combined_report(enriched)

        recs_text = " ".join(report["recommendations"]).lower()
        assert "blast radius" in recs_text or "incrementally" in recs_text


# ---------------------------------------------------------------------------
# CLI command tests (using CliRunner)
# ---------------------------------------------------------------------------


class TestOvermindEnrichCLI:
    def test_enrich_json_output_empty_file(self, tmp_path):
        from typer.testing import CliRunner
        from faultray.cli.main import app
        import importlib
        import faultray.cli.overmind_cmd  # ensure commands are registered

        runner = CliRunner()

        overmind_file = tmp_path / "overmind.json"
        overmind_file.write_text(json.dumps({}))

        result = runner.invoke(app, ["overmind", "enrich", str(overmind_file), "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "summary" in data
        assert "recommendations" in data

    def test_enrich_file_not_found(self, tmp_path):
        from typer.testing import CliRunner
        from faultray.cli.main import app
        import faultray.cli.overmind_cmd  # noqa: F401

        runner = CliRunner()
        result = runner.invoke(app, ["overmind", "enrich", str(tmp_path / "nonexistent.json")])
        assert result.exit_code != 0

    def test_enrich_invalid_json(self, tmp_path):
        from typer.testing import CliRunner
        from faultray.cli.main import app
        import faultray.cli.overmind_cmd  # noqa: F401

        runner = CliRunner()
        bad_file = tmp_path / "bad.json"
        bad_file.write_text("{not valid json")
        result = runner.invoke(app, ["overmind", "enrich", str(bad_file)])
        assert result.exit_code != 0

    def test_enrich_with_risks_and_changes(self, tmp_path):
        from typer.testing import CliRunner
        from faultray.cli.main import app
        import faultray.cli.overmind_cmd  # noqa: F401

        runner = CliRunner()
        data = _make_overmind_json(
            risks=[_make_risk("r1", "high", "High risk")],
            changes=[_make_change(directly_affected=["aws_instance.web"])],
        )
        overmind_file = tmp_path / "overmind.json"
        overmind_file.write_text(json.dumps(data))

        result = runner.invoke(app, ["overmind", "enrich", str(overmind_file), "--json"])
        assert result.exit_code == 0
        report = json.loads(result.output)
        assert report["summary"]["overmind_risks"] == 1
        assert report["summary"]["blast_radius_items"] == 1

    def test_enrich_html_output(self, tmp_path):
        from typer.testing import CliRunner
        from faultray.cli.main import app
        import faultray.cli.overmind_cmd  # noqa: F401

        runner = CliRunner()
        data = _make_overmind_json(risks=[_make_risk()])
        overmind_file = tmp_path / "overmind.json"
        overmind_file.write_text(json.dumps(data))
        html_file = tmp_path / "report.html"

        result = runner.invoke(
            app, ["overmind", "enrich", str(overmind_file), "--html", str(html_file)]
        )
        assert result.exit_code == 0
        assert html_file.exists()
        html_content = html_file.read_text()
        assert "FaultRay x Overmind" in html_content
        assert "<!DOCTYPE html>" in html_content


class TestOvermindCompareCLI:
    def test_compare_empty_model(self, tmp_path):
        from typer.testing import CliRunner
        from faultray.cli.main import app
        import faultray.cli.overmind_cmd  # noqa: F401

        runner = CliRunner()
        overmind_file = tmp_path / "overmind.json"
        data = _make_overmind_json(
            changes=[_make_change(directly_affected=["aws_instance.web"])]
        )
        overmind_file.write_text(json.dumps(data))

        # Create an empty YAML model file
        yaml_file = tmp_path / "infra.yaml"
        yaml_file.write_text("components: []\n")

        result = runner.invoke(
            app, ["overmind", "compare", str(overmind_file), str(yaml_file), "--json"]
        )
        assert result.exit_code == 0
        report = json.loads(result.output)
        assert report["total_blast_radius_items"] == 1
        assert report["unmapped_count"] == 1
        assert report["coverage_percent"] == 0.0

    def test_compare_file_not_found(self, tmp_path):
        from typer.testing import CliRunner
        from faultray.cli.main import app
        import faultray.cli.overmind_cmd  # noqa: F401

        runner = CliRunner()
        result = runner.invoke(
            app,
            [
                "overmind", "compare",
                str(tmp_path / "missing.json"),
                str(tmp_path / "infra.yaml"),
            ],
        )
        assert result.exit_code != 0

    def test_compare_zero_blast_radius(self, tmp_path):
        """When Overmind output has no changes, coverage should be 100%."""
        from typer.testing import CliRunner
        from faultray.cli.main import app
        import faultray.cli.overmind_cmd  # noqa: F401

        runner = CliRunner()
        overmind_file = tmp_path / "overmind.json"
        overmind_file.write_text(json.dumps(_make_overmind_json()))

        yaml_file = tmp_path / "infra.yaml"
        yaml_file.write_text("components: []\n")

        result = runner.invoke(
            app, ["overmind", "compare", str(overmind_file), str(yaml_file), "--json"]
        )
        assert result.exit_code == 0
        report = json.loads(result.output)
        assert report["coverage_percent"] == 100.0
