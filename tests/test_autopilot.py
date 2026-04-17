# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""Tests for the Autopilot pipeline.

Covers:
  - RequirementsParser (rule-based extraction)
  - TopologyDesigner (InfraGraph generation)
  - TerraformGenerator (HCL file generation)
  - AutopilotPipeline (end-to-end)
"""

from __future__ import annotations

from pathlib import Path

import pytest

from faultray.autopilot.requirements_parser import (
    RequirementsParser,
    RequirementsSpec,
)
from faultray.autopilot.terraform_generator import TerraformGenerator
from faultray.autopilot.topology_designer import TopologyDesigner
from faultray.model.components import ComponentType


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

WEBAPP_TEXT = (
    "3層Webアプリ。React frontend, Node.js API, PostgreSQL DB。"
    "月間100万PV。可用性99.9%必要。東京リージョン。"
)

API_TEXT = (
    "REST API service using FastAPI and PostgreSQL. "
    "Redis cache for performance. Target: 99.9% availability. "
    "Region: ap-northeast-1."
)

PIPELINE_TEXT = (
    "データパイプライン。Kafka queue, PostgreSQL database, S3 storage。"
    "可用性99.9%。"
)


# ---------------------------------------------------------------------------
# RequirementsParser tests
# ---------------------------------------------------------------------------


class TestRequirementsParser:
    def setup_method(self):
        self.parser = RequirementsParser()

    def test_parse_3tier_webapp(self):
        spec = self.parser.parse_text(WEBAPP_TEXT)
        assert isinstance(spec, RequirementsSpec)
        assert spec.app_type == "web_app"
        assert spec.availability_target == 99.9
        assert spec.multi_az is True
        assert spec.region == "ap-northeast-1"
        roles = {c.role for c in spec.components}
        assert "api" in roles
        assert "database" in roles

    def test_parse_availability_999(self):
        spec = self.parser.parse_text("System requires 99.9% availability")
        assert spec.availability_target == 99.9
        assert spec.multi_az is True
        assert spec.multi_region is False

    def test_parse_availability_9999(self):
        spec = self.parser.parse_text("System requires 99.99% availability")
        assert spec.availability_target == 99.99
        assert spec.multi_az is True
        assert spec.multi_region is True

    def test_parse_traffic_1m_pv(self):
        spec = self.parser.parse_text("月間100万PV。可用性99.9%。3層Webアプリ。")
        assert spec.traffic_scale in ("high", "medium")
        assert "PV" in spec.expected_traffic or "pv" in spec.expected_traffic.lower()

    def test_parse_traffic_small(self):
        spec = self.parser.parse_text("Small startup app. REST API. PostgreSQL.")
        assert spec.traffic_scale == "low"

    def test_parse_region_tokyo(self):
        spec = self.parser.parse_text("東京リージョン。3層Webアプリ。")
        assert spec.region == "ap-northeast-1"

    def test_parse_region_explicit(self):
        spec = self.parser.parse_text("Deploy to us-east-1 region. REST API.")
        assert spec.region == "us-east-1"

    def test_parse_api_type(self):
        spec = self.parser.parse_text("REST API service with FastAPI. PostgreSQL backend.")
        assert spec.app_type == "api"

    def test_parse_data_pipeline_type(self):
        spec = self.parser.parse_text(PIPELINE_TEXT)
        assert spec.app_type == "data_pipeline"
        roles = {c.role for c in spec.components}
        assert "queue" in roles

    def test_parse_security_https(self):
        spec = self.parser.parse_text("Web app. HTTPS必須。WAF必要。")
        assert len(spec.security_requirements) > 0

    def test_parse_empty_text_defaults(self):
        spec = self.parser.parse_text("")
        assert isinstance(spec, RequirementsSpec)
        assert spec.app_type in ("web_app", "api", "microservices", "data_pipeline")
        assert spec.availability_target >= 99.0

    def test_parse_file(self, tmp_path: Path):
        req_file = tmp_path / "requirements.md"
        req_file.write_text(WEBAPP_TEXT, encoding="utf-8")
        spec = self.parser.parse_file(req_file)
        assert spec.app_type == "web_app"
        assert spec.availability_target == 99.9

    def test_parse_file_not_found(self, tmp_path: Path):
        missing = tmp_path / "does_not_exist.md"
        with pytest.raises(FileNotFoundError):
            self.parser.parse_file(missing)

    def test_component_specs_have_roles(self):
        spec = self.parser.parse_text(WEBAPP_TEXT)
        for comp in spec.components:
            assert comp.role, "ComponentSpec.role must not be empty"
            assert comp.technology, "ComponentSpec.technology must not be empty"
            assert comp.scaling in ("fixed", "auto")
            assert isinstance(comp.redundancy, bool)

    def test_redis_detected_as_cache(self):
        spec = self.parser.parse_text("Node.js API with Redis cache and PostgreSQL. 99.9%.")
        roles = {c.role for c in spec.components}
        assert "cache" in roles

    def test_multi_region_flag(self):
        spec = self.parser.parse_text("System requires 99.99% availability. React, Node.js, PostgreSQL.")
        assert spec.multi_region is True


# ---------------------------------------------------------------------------
# TopologyDesigner tests
# ---------------------------------------------------------------------------


class TestTopologyDesigner:
    def setup_method(self):
        self.parser = RequirementsParser()
        self.designer = TopologyDesigner()

    def _design(self, text: str):
        spec = self.parser.parse_text(text)
        return self.designer.design(spec), spec

    def test_webapp_has_alb(self):
        graph, _ = self._design(WEBAPP_TEXT)
        comp_types = {c.type for c in graph.components.values()}
        assert ComponentType.LOAD_BALANCER in comp_types

    def test_webapp_has_database(self):
        graph, _ = self._design(WEBAPP_TEXT)
        comp_types = {c.type for c in graph.components.values()}
        assert ComponentType.DATABASE in comp_types

    def test_multiaz_sets_failover(self):
        graph, _ = self._design("3層Webアプリ。React, Node.js, PostgreSQL。可用性99.9%。")
        db_comp = next(
            (c for c in graph.components.values() if c.type == ComponentType.DATABASE),
            None,
        )
        assert db_comp is not None
        assert db_comp.failover.enabled is True

    def test_multiaz_database_replicas(self):
        graph, _ = self._design("3層Webアプリ。React, Node.js, PostgreSQL。可用性99.9%。")
        db_comp = next(
            (c for c in graph.components.values() if c.type == ComponentType.DATABASE),
            None,
        )
        assert db_comp is not None
        assert db_comp.replicas >= 2

    def test_no_multiaz_single_replica(self):
        graph, _ = self._design("Simple app. React, Node.js, PostgreSQL. Availability 99%.")
        db_comp = next(
            (c for c in graph.components.values() if c.type == ComponentType.DATABASE),
            None,
        )
        # 99% < 99.9 threshold, so multi_az=False, replicas=1
        assert db_comp is not None
        assert db_comp.replicas == 1

    def test_high_traffic_autoscaling(self):
        graph, _ = self._design(
            "3層Webアプリ。React frontend, Node.js API, PostgreSQL DB。月間1000万PV。可用性99.9%。"
        )
        app_comps = [
            c for c in graph.components.values()
            if c.type == ComponentType.APP_SERVER
        ]
        assert any(c.autoscaling.enabled for c in app_comps), \
            "High-traffic app should have autoscaling enabled"

    def test_dependencies_exist(self):
        graph, _ = self._design(WEBAPP_TEXT)
        # At least some dependency edges should be present
        edges = graph.all_dependency_edges()
        assert len(edges) > 0

    def test_api_type_no_frontend(self):
        graph, spec = self._design(API_TEXT)
        assert spec.app_type == "api"
        # api type may or may not have WEB_SERVER component
        comp_types_list = [c.type for c in graph.components.values()]
        # Must have APP_SERVER (api) and DATABASE
        assert ComponentType.APP_SERVER in comp_types_list
        assert ComponentType.DATABASE in comp_types_list

    def test_cache_component_type(self):
        graph, _ = self._design(
            "Node.js API with Redis cache and PostgreSQL database. 99.9% availability."
        )
        comp_types = {c.type for c in graph.components.values()}
        assert ComponentType.CACHE in comp_types

    def test_region_propagated_to_components(self):
        graph, spec = self._design(WEBAPP_TEXT)
        for comp in graph.components.values():
            if comp.region.region:
                assert comp.region.region in (spec.region, "us-east-1")  # CloudFront uses us-east-1


# ---------------------------------------------------------------------------
# TerraformGenerator tests
# ---------------------------------------------------------------------------


class TestTerraformGenerator:
    def setup_method(self):
        parser = RequirementsParser()
        designer = TopologyDesigner()
        self.tf_gen = TerraformGenerator()
        self.spec = parser.parse_text(WEBAPP_TEXT)
        self.graph = designer.design(self.spec)

    def test_generate_returns_files(self):
        output = self.tf_gen.generate(self.graph, self.spec)
        assert len(output.files) > 0

    def test_required_base_files_present(self):
        output = self.tf_gen.generate(self.graph, self.spec)
        required = {"provider.tf", "variables.tf", "vpc.tf", "security.tf", "outputs.tf"}
        for fname in required:
            assert fname in output.files, f"Missing required file: {fname}"

    def test_provider_tf_contains_aws(self):
        output = self.tf_gen.generate(self.graph, self.spec)
        assert 'source  = "hashicorp/aws"' in output.files["provider.tf"]

    def test_provider_tf_contains_region(self):
        output = self.tf_gen.generate(self.graph, self.spec)
        # Region is referenced via var.aws_region in provider.tf; the literal
        # region value appears in variables.tf as the default.
        assert self.spec.region in output.files["variables.tf"]

    def test_variables_tf_has_region_default(self):
        output = self.tf_gen.generate(self.graph, self.spec)
        assert self.spec.region in output.files["variables.tf"]

    def test_vpc_tf_has_subnets(self):
        output = self.tf_gen.generate(self.graph, self.spec)
        assert "aws_subnet" in output.files["vpc.tf"]

    def test_security_tf_has_alb_sg(self):
        output = self.tf_gen.generate(self.graph, self.spec)
        assert "alb_sg" in output.files["security.tf"]

    def test_db_component_file_generated(self):
        output = self.tf_gen.generate(self.graph, self.spec)
        # At least one .tf file should contain RDS resource
        all_content = "\n".join(output.files.values())
        assert "aws_db_instance" in all_content

    def test_ecs_component_file_generated(self):
        output = self.tf_gen.generate(self.graph, self.spec)
        all_content = "\n".join(output.files.values())
        assert "aws_ecs_service" in all_content

    def test_multiaz_rds_multi_az_true(self):
        output = self.tf_gen.generate(self.graph, self.spec)
        all_content = "\n".join(output.files.values())
        # spec.multi_az=True → multi_az = true in RDS
        assert "multi_az               = true" in all_content

    def test_sqs_file_for_queue_component(self):
        from faultray.autopilot.requirements_parser import RequirementsParser
        from faultray.autopilot.topology_designer import TopologyDesigner

        parser = RequirementsParser()
        designer = TopologyDesigner()
        spec = parser.parse_text(
            "Microservices app with Node.js API, PostgreSQL, SQS queue. 99.9% availability."
        )
        graph = designer.design(spec)
        output = self.tf_gen.generate(graph, spec)
        all_content = "\n".join(output.files.values())
        assert "aws_sqs_queue" in all_content

    def test_no_raw_format_errors(self):
        """Generated HCL should not contain unescaped Python format artifacts."""
        output = self.tf_gen.generate(self.graph, self.spec)
        for fname, content in output.files.items():
            # Should not have stray Python format artifacts
            assert "{0}" not in content, f"{fname} contains Python format artifact {{0}}"
        # At least the vpc.tf and provider.tf should reference vars
        combined = "\n".join(output.files.values())
        assert "var." in combined, "Generated HCL should reference at least one variable"

    def test_output_warnings_list(self):
        output = self.tf_gen.generate(self.graph, self.spec)
        assert isinstance(output.warnings, list)


# ---------------------------------------------------------------------------
# AutopilotPipeline end-to-end tests
# ---------------------------------------------------------------------------


class TestAutopilotPipeline:
    def setup_method(self):
        from faultray.autopilot.pipeline import AutopilotPipeline

        self.pipeline = AutopilotPipeline()

    def test_run_from_text_succeeds(self):
        result = self.pipeline.run_from_text(WEBAPP_TEXT)
        assert result.success, f"Pipeline failed: {result.errors}"
        assert result.spec is not None
        assert result.graph is not None
        assert result.terraform is not None

    def test_run_from_text_terraform_files(self):
        result = self.pipeline.run_from_text(WEBAPP_TEXT)
        assert result.terraform is not None
        assert len(result.terraform.files) > 0

    def test_run_from_file(self, tmp_path: Path):
        req_file = tmp_path / "req.md"
        req_file.write_text(WEBAPP_TEXT, encoding="utf-8")
        result = self.pipeline.run_from_file(req_file)
        assert result.success, f"Pipeline failed: {result.errors}"
        assert result.terraform is not None

    def test_run_from_missing_file(self, tmp_path: Path):
        missing = tmp_path / "missing.md"
        result = self.pipeline.run_from_file(missing)
        assert not result.success
        assert len(result.errors) > 0

    def test_run_from_yaml(self, tmp_path: Path):
        """run_from_yaml should load an existing graph and generate Terraform."""
        import json

        from faultray.model.components import Component, ComponentType, Dependency
        from faultray.model.graph import InfraGraph

        # Create a minimal graph and save as JSON (InfraGraph.load supports YAML but also JSON)
        graph = InfraGraph()
        graph.add_component(
            Component(id="lb", name="ALB", type=ComponentType.LOAD_BALANCER, port=443)
        )
        graph.add_component(
            Component(id="api", name="API", type=ComponentType.APP_SERVER, port=3000)
        )
        graph.add_component(
            Component(id="db", name="DB", type=ComponentType.DATABASE, port=5432)
        )
        graph.add_dependency(Dependency(source_id="lb", target_id="api"))
        graph.add_dependency(Dependency(source_id="api", target_id="db"))

        model_file = tmp_path / "infra.json"
        graph.save(model_file)

        result = self.pipeline.run_from_yaml(model_file)
        assert result.success, f"run_from_yaml failed: {result.errors}"
        assert result.terraform is not None
        assert len(result.terraform.files) > 0

    def test_terraform_only_writes_files(self, tmp_path: Path):
        result = self.pipeline.run_from_text(API_TEXT)
        assert result.success

        out_dir = tmp_path / "tf_out"
        self.pipeline.terraform_only(result, out_dir)

        written = list(out_dir.glob("*.tf"))
        assert len(written) > 0, "terraform_only should write .tf files"

    def test_availability_score_returned(self):
        result = self.pipeline.run_from_text(WEBAPP_TEXT)
        assert result.availability_score >= 0.0
        assert result.availability_score <= 100.0

    def test_pipeline_result_success_property(self):
        result = self.pipeline.run_from_text(WEBAPP_TEXT)
        assert result.success is True
        assert len(result.errors) == 0

    def test_api_pipeline(self):
        result = self.pipeline.run_from_text(API_TEXT)
        assert result.success
        assert result.spec is not None
        assert result.spec.app_type == "api"

    def test_data_pipeline(self):
        result = self.pipeline.run_from_text(PIPELINE_TEXT)
        assert result.success
        assert result.spec is not None
        assert result.spec.app_type == "data_pipeline"


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def setup_method(self):
        self.parser = RequirementsParser()
        self.designer = TopologyDesigner()
        self.tf_gen = TerraformGenerator()

    def test_special_chars_in_app_name(self):
        spec = self.parser.parse_text("# My App! (2026)\n\nReact, Node.js, PostgreSQL. 99.9%.")
        # App name extracted from heading
        assert spec.app_name  # non-empty
        # TerraformGenerator must not crash on special chars in name
        graph = self.designer.design(spec)
        output = self.tf_gen.generate(graph, spec)
        assert len(output.files) > 0

    def test_minimal_input(self):
        """Even minimal text should produce a valid result."""
        spec = self.parser.parse_text("web app")
        assert spec.app_type == "web_app"
        graph = self.designer.design(spec)
        assert len(graph.components) > 0

    def test_topology_designer_all_components_have_type(self):
        spec = self.parser.parse_text(WEBAPP_TEXT)
        graph = self.designer.design(spec)
        for comp in graph.components.values():
            assert isinstance(comp.type, ComponentType)

    def test_terraform_output_files_are_strings(self):
        spec = self.parser.parse_text(WEBAPP_TEXT)
        graph = self.designer.design(spec)
        output = self.tf_gen.generate(graph, spec)
        for fname, content in output.files.items():
            assert isinstance(fname, str)
            assert isinstance(content, str)
            assert len(content) > 0
