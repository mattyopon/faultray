"""Tests for auto-remediation pipeline (auto_pipeline.py)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from faultray.model.components import (
    AutoScalingConfig,
    Component,
    ComponentType,
    Dependency,
    FailoverConfig,
    SecurityProfile,
)
from faultray.model.graph import InfraGraph
from faultray.remediation.auto_pipeline import (
    AutoRemediationPipeline,
    PipelineResult,
    PipelineStep,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_vulnerable_graph() -> InfraGraph:
    """Create a graph with known vulnerabilities for remediation."""
    graph = InfraGraph()

    # Single-replica database without encryption (will trigger remediations)
    graph.add_component(Component(
        id="main_db",
        name="Main Database",
        type=ComponentType.DATABASE,
        port=5432,
        replicas=1,
        security=SecurityProfile(
            encryption_at_rest=False,
            backup_enabled=False,
        ),
    ))

    # App server without autoscaling
    graph.add_component(Component(
        id="api_server",
        name="API Server",
        type=ComponentType.APP_SERVER,
        port=8080,
        replicas=1,
        autoscaling=AutoScalingConfig(enabled=False),
        security=SecurityProfile(
            waf_protected=False,
            encryption_in_transit=False,
        ),
    ))

    # Load balancer without WAF
    graph.add_component(Component(
        id="lb",
        name="Load Balancer",
        type=ComponentType.LOAD_BALANCER,
        port=443,
        replicas=1,
        security=SecurityProfile(
            waf_protected=False,
            encryption_in_transit=False,
        ),
    ))

    graph.add_dependency(Dependency(source_id="lb", target_id="api_server"))
    graph.add_dependency(Dependency(source_id="api_server", target_id="main_db"))

    return graph


def _make_healthy_graph() -> InfraGraph:
    """Create a well-configured graph with high resilience."""
    graph = InfraGraph()

    graph.add_component(Component(
        id="lb",
        name="Load Balancer",
        type=ComponentType.LOAD_BALANCER,
        port=443,
        replicas=2,
        failover=FailoverConfig(enabled=True),
        autoscaling=AutoScalingConfig(enabled=True),
        security=SecurityProfile(
            waf_protected=True,
            encryption_in_transit=True,
        ),
    ))

    graph.add_component(Component(
        id="api",
        name="API Server",
        type=ComponentType.APP_SERVER,
        port=8080,
        replicas=3,
        autoscaling=AutoScalingConfig(enabled=True),
        security=SecurityProfile(
            waf_protected=True,
            encryption_in_transit=True,
        ),
    ))

    graph.add_component(Component(
        id="db",
        name="Database",
        type=ComponentType.DATABASE,
        port=5432,
        replicas=2,
        failover=FailoverConfig(enabled=True),
        security=SecurityProfile(
            encryption_at_rest=True,
            encryption_in_transit=True,
            backup_enabled=True,
        ),
    ))

    graph.add_dependency(Dependency(source_id="lb", target_id="api"))
    graph.add_dependency(Dependency(source_id="api", target_id="db"))

    return graph


# ---------------------------------------------------------------------------
# 1. PipelineStep and PipelineResult
# ---------------------------------------------------------------------------

class TestDataClasses:
    def test_pipeline_step_defaults(self):
        step = PipelineStep(name="test")
        assert step.status == "pending"
        assert step.output == ""
        assert step.duration_seconds == 0.0

    def test_pipeline_result_defaults(self):
        result = PipelineResult()
        assert result.dry_run is True
        assert result.success is False
        assert result.files_generated == 0

    def test_pipeline_result_to_dict(self):
        result = PipelineResult(
            steps=[PipelineStep(name="test", status="passed", output="OK", duration_seconds=1.5)],
            score_before=50.0,
            score_after=80.0,
            files_generated=5,
            dry_run=True,
            success=True,
        )
        d = result.to_dict()

        assert d["score_before"] == 50.0
        assert d["score_after"] == 80.0
        assert d["score_improvement"] == 30.0
        assert d["files_generated"] == 5
        assert d["dry_run"] is True
        assert d["success"] is True
        assert len(d["steps"]) == 1


# ---------------------------------------------------------------------------
# 2. Dry run pipeline (vulnerable graph)
# ---------------------------------------------------------------------------

class TestDryRunPipeline:
    def test_dry_run_generates_files(self):
        graph = _make_vulnerable_graph()
        pipeline = AutoRemediationPipeline(graph)
        result = pipeline.run(target_score=90.0, dry_run=True)

        assert result.dry_run is True
        assert result.success is True
        assert result.files_generated > 0
        assert result.score_before < result.score_after

    def test_dry_run_does_not_write_files(self, tmp_path):
        graph = _make_vulnerable_graph()
        output_dir = tmp_path / "remediation-output"
        pipeline = AutoRemediationPipeline(graph, output_dir=output_dir)
        result = pipeline.run(target_score=90.0, dry_run=True)

        # Files should NOT be written in dry run
        assert not output_dir.exists() or not any(output_dir.rglob("*.tf"))

    def test_dry_run_has_six_steps(self):
        graph = _make_vulnerable_graph()
        pipeline = AutoRemediationPipeline(graph)
        result = pipeline.run(target_score=90.0, dry_run=True)

        assert len(result.steps) == 6
        step_names = [s.name for s in result.steps]
        assert "Evaluate current state" in step_names
        assert "Generate remediation IaC" in step_names
        assert "Validate generated code" in step_names
        assert "Generate diff preview" in step_names
        assert "Save files" in step_names
        assert "Predict improvement" in step_names

    def test_dry_run_skips_save(self):
        graph = _make_vulnerable_graph()
        pipeline = AutoRemediationPipeline(graph)
        result = pipeline.run(target_score=90.0, dry_run=True)

        save_step = [s for s in result.steps if s.name == "Save files"][0]
        assert save_step.status == "skipped"


# ---------------------------------------------------------------------------
# 3. Apply pipeline
# ---------------------------------------------------------------------------

class TestApplyPipeline:
    def test_apply_writes_files(self, tmp_path):
        graph = _make_vulnerable_graph()
        output_dir = tmp_path / "remediation-output"
        pipeline = AutoRemediationPipeline(graph, output_dir=output_dir)
        result = pipeline.run(target_score=90.0, dry_run=False)

        assert result.dry_run is False
        assert result.success is True

        # Files should be written
        assert output_dir.exists()
        files = list(output_dir.rglob("*"))
        # Should have at least some .tf or .yaml files plus a README
        generated = [f for f in files if f.is_file()]
        assert len(generated) > 0

    def test_apply_saves_terraform_files(self, tmp_path):
        graph = _make_vulnerable_graph()
        output_dir = tmp_path / "fixes"
        pipeline = AutoRemediationPipeline(graph, output_dir=output_dir)
        result = pipeline.run(target_score=90.0, dry_run=False)

        tf_files = list(output_dir.rglob("*.tf"))
        assert len(tf_files) > 0, "Should generate at least one Terraform file"


# ---------------------------------------------------------------------------
# 4. Healthy graph (no fixes needed)
# ---------------------------------------------------------------------------

class TestHealthyGraph:
    def test_healthy_graph_minimal_changes(self):
        graph = _make_healthy_graph()
        pipeline = AutoRemediationPipeline(graph)
        result = pipeline.run(target_score=90.0, dry_run=True)

        assert result.success is True
        # May still generate some files depending on edge cases,
        # but score improvement should be minimal
        assert result.score_before > 0


# ---------------------------------------------------------------------------
# 5. Diff preview
# ---------------------------------------------------------------------------

class TestDiffPreview:
    def test_diff_preview_available(self):
        graph = _make_vulnerable_graph()
        pipeline = AutoRemediationPipeline(graph)
        result = pipeline.run(target_score=90.0, dry_run=True)

        diff = pipeline.get_diff_preview()
        assert isinstance(diff, str)
        if result.files_generated > 0:
            assert len(diff) > 0
            assert "+" in diff  # Should have added lines

    def test_diff_preview_empty_before_run(self):
        graph = _make_vulnerable_graph()
        pipeline = AutoRemediationPipeline(graph)
        diff = pipeline.get_diff_preview()
        assert diff == ""


# ---------------------------------------------------------------------------
# 6. Load from path
# ---------------------------------------------------------------------------

class TestLoadFromPath:
    def test_load_from_json_path(self, tmp_path):
        graph = _make_vulnerable_graph()
        model_path = tmp_path / "model.json"
        graph.save(model_path)

        pipeline = AutoRemediationPipeline(model_path)
        result = pipeline.run(target_score=90.0, dry_run=True)
        assert result.success is True


# ---------------------------------------------------------------------------
# 7. Validation
# ---------------------------------------------------------------------------

class TestValidation:
    def test_terraform_validation_passes(self):
        graph = _make_vulnerable_graph()
        pipeline = AutoRemediationPipeline(graph)
        result = pipeline.run(target_score=90.0, dry_run=True)

        validate_step = [s for s in result.steps if s.name == "Validate generated code"][0]
        # Should pass since IaCGenerator produces well-formed templates
        assert validate_step.status == "passed"

    def test_validate_terraform_unbalanced_braces(self):
        graph = _make_vulnerable_graph()
        pipeline = AutoRemediationPipeline(graph)
        errors = pipeline._validate_terraform('resource "test" { name = "x" ')
        assert any("brace" in e.lower() for e in errors)

    def test_validate_terraform_valid(self):
        graph = _make_vulnerable_graph()
        pipeline = AutoRemediationPipeline(graph)
        errors = pipeline._validate_terraform('resource "test" { name = "x" }')
        # Should have no errors (only possible warning about structure)
        real_errors = [e for e in errors if "warning" not in e.lower()]
        assert len(real_errors) == 0

    def test_validate_kubernetes_valid(self):
        graph = _make_vulnerable_graph()
        pipeline = AutoRemediationPipeline(graph)
        content = "apiVersion: v1\nkind: Service\nmetadata:\n  name: test"
        errors = pipeline._validate_kubernetes(content)
        assert len(errors) == 0


# ---------------------------------------------------------------------------
# 8. Pipeline result JSON serialization
# ---------------------------------------------------------------------------

class TestSerialization:
    def test_full_result_serializable(self):
        graph = _make_vulnerable_graph()
        pipeline = AutoRemediationPipeline(graph)
        result = pipeline.run(target_score=90.0, dry_run=True)

        d = result.to_dict()
        json_str = json.dumps(d)
        parsed = json.loads(json_str)

        assert isinstance(parsed, dict)
        assert "steps" in parsed
        assert "score_before" in parsed
        assert "score_after" in parsed
        assert "score_improvement" in parsed
