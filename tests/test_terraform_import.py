# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""Tests for ``faultray import terraform`` (discovery.terraform_import).

Contract under test:
- the three input formats (show -json state / show -json plan / raw
  tfstate v4) all normalise into the same component model;
- dependency edges appear only with evidence, with conservative
  ``requires`` semantics, and never form a cycle;
- pattern wiring (ALB, Lambda ESM, ECS task definitions) produces edges
  in the semantically correct direction even when raw references point
  the other way;
- the emitted YAML round-trips through the model loader into simulate.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from faultray.discovery.terraform_import import (
    import_terraform,
    load_terraform_file,
    topology_yaml,
)
from faultray.model.components import ComponentType
from faultray.model.loader import load_yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
SAMPLE_STATE = REPO_ROOT / "examples" / "terraform-import" / "sample-state.json"


def _edge_pairs(result) -> set[tuple[str, str]]:
    return {(e.source, e.target) for e in result.edges}


@pytest.fixture(scope="module")
def sample_result():
    assert SAMPLE_STATE.exists(), f"fixture missing: {SAMPLE_STATE}"
    return load_terraform_file(SAMPLE_STATE)


# ---------------------------------------------------------------------------
# State import (terraform show -json format)
# ---------------------------------------------------------------------------


class TestStateImport:
    def test_component_type_mapping(self, sample_result):
        comps = sample_result.graph.components
        expected = {
            "aws_lb.app": ComponentType.LOAD_BALANCER,
            "aws_instance.static_web": ComponentType.APP_SERVER,
            "aws_ecs_service.api": ComponentType.APP_SERVER,
            "aws_db_instance.main": ComponentType.DATABASE,
            "aws_elasticache_replication_group.cache": ComponentType.CACHE,
            "aws_sqs_queue.jobs": ComponentType.QUEUE,
            "aws_s3_bucket.assets": ComponentType.STORAGE,
            "aws_route53_record.app": ComponentType.DNS,
            "aws_lambda_function.worker": ComponentType.SERVERLESS,
        }
        for comp_id, comp_type in expected.items():
            assert comp_id in comps, f"missing component {comp_id}"
            assert comps[comp_id].type == comp_type

    def test_source_format_detected(self, sample_result):
        assert sample_result.source_format == "state"

    def test_pass_through_resources_are_not_components(self, sample_result):
        comps = sample_result.graph.components
        for addr in comps:
            assert "target_group" not in addr
            assert "listener" not in addr
            assert "task_definition" not in addr
            assert "event_source_mapping" not in addr

    def test_unmapped_types_counted_not_imported(self, sample_result):
        assert sample_result.skipped_types == {"aws_security_group": 1}
        assert "aws_security_group.app" not in sample_result.graph.components

    def test_replicas_extraction(self, sample_result):
        comps = sample_result.graph.components
        assert comps["aws_ecs_service.api"].replicas == 3  # desired_count
        assert comps["aws_db_instance.main"].replicas == 2  # multi_az
        assert (
            comps["aws_elasticache_replication_group.cache"].replicas == 2
        )  # num_cache_clusters

    def test_endpoint_becomes_host(self, sample_result):
        db = sample_result.graph.components["aws_db_instance.main"]
        assert db.host == "appdb.c1a2b3c4d5e6.ap-northeast-1.rds.amazonaws.com"
        assert db.port == 5432

    def test_managed_service_sla_attached(self, sample_result):
        comps = sample_result.graph.components
        assert comps["aws_s3_bucket.assets"].external_sla is not None
        assert comps["aws_s3_bucket.assets"].external_sla.provider_sla == 99.9
        assert comps["aws_sqs_queue.jobs"].external_sla is not None
        # Compute components carry no provider SLA.
        assert comps["aws_ecs_service.api"].external_sla is None
        assert comps["aws_instance.static_web"].external_sla is None

    def test_no_isolated_components_in_wired_stack(self, sample_result):
        assert sample_result.isolated_component_ids == []
        assert sample_result.warnings == []


class TestEdgeInference:
    def test_alb_wiring_direction_lb_to_backend(self, sample_result):
        pairs = _edge_pairs(sample_result)
        assert ("aws_lb.app", "aws_ecs_service.api") in pairs
        assert ("aws_ecs_service.api", "aws_lb.app") not in pairs

    def test_alb_listener_rule_chain_wires_ec2(self, sample_result):
        # rule → listener → LB chain plus attachment target_id matching
        pairs = _edge_pairs(sample_result)
        assert ("aws_lb.app", "aws_instance.static_web") in pairs

    def test_dns_depends_on_lb(self, sample_result):
        assert ("aws_route53_record.app", "aws_lb.app") in _edge_pairs(sample_result)

    def test_task_definition_collapsed_into_service_edges(self, sample_result):
        pairs = _edge_pairs(sample_result)
        svc = "aws_ecs_service.api"
        assert (svc, "aws_db_instance.main") in pairs
        assert (svc, "aws_elasticache_replication_group.cache") in pairs
        assert (svc, "aws_sqs_queue.jobs") in pairs
        assert (svc, "aws_s3_bucket.assets") in pairs

    def test_lambda_event_source_mapping_consumer_requires_queue(
        self, sample_result
    ):
        pairs = _edge_pairs(sample_result)
        assert ("aws_lambda_function.worker", "aws_sqs_queue.jobs") in pairs
        assert ("aws_sqs_queue.jobs", "aws_lambda_function.worker") not in pairs

    def test_lambda_env_endpoint_reference(self, sample_result):
        assert (
            "aws_lambda_function.worker",
            "aws_db_instance.main",
        ) in _edge_pairs(sample_result)

    def test_all_edge_types_conservatively_requires(self, sample_result):
        assert {e.dep_type for e in sample_result.edges} == {"requires"}

    def test_every_edge_has_evidence(self, sample_result):
        for edge in sample_result.edges:
            assert edge.evidence


class TestExternalApis:
    def test_external_https_urls_become_external_api_components(
        self, sample_result
    ):
        comps = sample_result.graph.components
        assert "external:api.stripe.com" in comps
        assert comps["external:api.stripe.com"].type == ComponentType.EXTERNAL_API
        assert comps["external:api.stripe.com"].external_sla is not None
        assert "external:api.sendgrid.com" in comps

    def test_consumers_wired_to_external_apis(self, sample_result):
        pairs = _edge_pairs(sample_result)
        assert ("aws_ecs_service.api", "external:api.stripe.com") in pairs
        assert ("aws_lambda_function.worker", "external:api.sendgrid.com") in pairs

    def test_aws_urls_not_treated_as_external(self, sample_result):
        # The task definition env contains an SQS https URL — it must map to
        # the queue component, never to a synthetic external host.
        for comp_id in sample_result.graph.components:
            assert "amazonaws.com" not in comp_id


# ---------------------------------------------------------------------------
# Plan import (terraform show -json <planfile>)
# ---------------------------------------------------------------------------


def _plan_fixture() -> dict:
    """Plan whose values carry no computed IDs — edges must come from
    configuration references."""
    return {
        "format_version": "1.2",
        "planned_values": {
            "root_module": {
                "resources": [
                    {
                        "address": "aws_lb.web",
                        "type": "aws_lb",
                        "name": "web",
                        "values": {"name": "web-alb"},
                    },
                    {
                        "address": "aws_ecs_service.app",
                        "type": "aws_ecs_service",
                        "name": "app",
                        "values": {"name": "app", "desired_count": 2},
                    },
                    {
                        "address": "aws_ecs_task_definition.app",
                        "type": "aws_ecs_task_definition",
                        "name": "app",
                        "values": {"family": "app"},
                    },
                    {
                        "address": "aws_lb_target_group.app",
                        "type": "aws_lb_target_group",
                        "name": "app",
                        "values": {"name": "app-tg"},
                    },
                    {
                        "address": "aws_lb_listener.https",
                        "type": "aws_lb_listener",
                        "name": "https",
                        "values": {"port": 443},
                    },
                    {
                        "address": "aws_db_instance.main",
                        "type": "aws_db_instance",
                        "name": "main",
                        "values": {"identifier": "main", "engine": "postgres"},
                    },
                ]
            }
        },
        "configuration": {
            "root_module": {
                "resources": [
                    {
                        "address": "aws_lb_listener.https",
                        "type": "aws_lb_listener",
                        "name": "https",
                        "expressions": {
                            "load_balancer_arn": {
                                "references": ["aws_lb.web.arn", "aws_lb.web"]
                            },
                            "default_action": [
                                {
                                    "target_group_arn": {
                                        "references": [
                                            "aws_lb_target_group.app.arn",
                                            "aws_lb_target_group.app",
                                        ]
                                    }
                                }
                            ],
                        },
                    },
                    {
                        "address": "aws_ecs_service.app",
                        "type": "aws_ecs_service",
                        "name": "app",
                        "expressions": {
                            "task_definition": {
                                "references": [
                                    "aws_ecs_task_definition.app.arn",
                                    "aws_ecs_task_definition.app",
                                ]
                            },
                            "load_balancer": [
                                {
                                    "target_group_arn": {
                                        "references": [
                                            "aws_lb_target_group.app.arn",
                                            "aws_lb_target_group.app",
                                        ]
                                    }
                                }
                            ],
                        },
                    },
                    {
                        "address": "aws_ecs_task_definition.app",
                        "type": "aws_ecs_task_definition",
                        "name": "app",
                        "expressions": {
                            "container_definitions": {
                                "references": [
                                    "aws_db_instance.main.endpoint",
                                    "aws_db_instance.main",
                                ]
                            }
                        },
                    },
                ]
            }
        },
    }


class TestPlanImport:
    def test_detected_as_plan(self):
        result = import_terraform(_plan_fixture())
        assert result.source_format == "plan"

    def test_components_from_planned_values(self):
        result = import_terraform(_plan_fixture())
        assert set(result.graph.components) == {
            "aws_lb.web",
            "aws_ecs_service.app",
            "aws_db_instance.main",
        }

    def test_edges_from_configuration_references(self):
        result = import_terraform(_plan_fixture())
        pairs = _edge_pairs(result)
        # LB wiring via config refs only (no computed ARNs at plan time)
        assert ("aws_lb.web", "aws_ecs_service.app") in pairs
        # task definition collapse via config refs
        assert ("aws_ecs_service.app", "aws_db_instance.main") in pairs
        # raw reference direction must not leak: service never requires LB
        assert ("aws_ecs_service.app", "aws_lb.web") not in pairs


# ---------------------------------------------------------------------------
# Raw tfstate (version 4)
# ---------------------------------------------------------------------------


def _tfstate_fixture() -> dict:
    return {
        "version": 4,
        "terraform_version": "1.9.0",
        "resources": [
            {
                "mode": "managed",
                "type": "aws_instance",
                "name": "web",
                "instances": [
                    {
                        "index_key": 0,
                        "attributes": {"id": "i-0000000000000aaaa", "instance_type": "t3.micro"},
                    },
                    {
                        "index_key": 1,
                        "attributes": {"id": "i-0000000000000bbbb", "instance_type": "t3.micro"},
                    },
                ],
            },
            {
                "mode": "managed",
                "type": "aws_db_instance",
                "name": "db",
                "instances": [
                    {
                        "attributes": {
                            "id": "db1",
                            "address": "db1.abcdefghij.ap-northeast-1.rds.amazonaws.com",
                            "engine": "mysql",
                        }
                    }
                ],
            },
            {
                "mode": "managed",
                "type": "aws_s3_bucket",
                "name": "logs",
                "instances": [
                    {
                        "attributes": {"bucket": "logs-bucket-x"},
                        "dependencies": ["aws_db_instance.db"],
                    }
                ],
            },
            {
                "mode": "data",
                "type": "aws_instance",
                "name": "ignored",
                "instances": [{"attributes": {"id": "i-0000000000000cccc"}}],
            },
        ],
    }


class TestTfstateV4:
    def test_indexed_instances_become_separate_components(self):
        result = import_terraform(_tfstate_fixture())
        assert "aws_instance.web[0]" in result.graph.components
        assert "aws_instance.web[1]" in result.graph.components

    def test_data_resources_ignored(self):
        result = import_terraform(_tfstate_fixture())
        assert len([c for c in result.graph.components if "ignored" in c]) == 0

    def test_instance_dependencies_create_edges(self):
        result = import_terraform(_tfstate_fixture())
        assert ("aws_s3_bucket.logs", "aws_db_instance.db") in _edge_pairs(result)

    def test_mysql_engine_port(self):
        result = import_terraform(_tfstate_fixture())
        assert result.graph.components["aws_db_instance.db"].port == 3306


# ---------------------------------------------------------------------------
# Conservative guarantees
# ---------------------------------------------------------------------------


class TestConservativeGuarantees:
    def test_no_edges_without_evidence(self):
        # Two unrelated resources: importing must NOT invent app→db edges
        # the way type-heuristic cross joins would.
        data = {
            "values": {
                "root_module": {
                    "resources": [
                        {
                            "address": "aws_instance.a",
                            "type": "aws_instance",
                            "name": "a",
                            "values": {"id": "i-0000000000001111a"},
                        },
                        {
                            "address": "aws_db_instance.b",
                            "type": "aws_db_instance",
                            "name": "b",
                            "values": {"id": "dbb"},
                        },
                    ]
                }
            }
        }
        result = import_terraform(data)
        assert result.edges == []
        assert set(result.isolated_component_ids) == {
            "aws_instance.a",
            "aws_db_instance.b",
        }

    def test_mutual_references_break_cycle_with_warning(self):
        data = {
            "values": {
                "root_module": {
                    "resources": [
                        {
                            "address": "aws_instance.a",
                            "type": "aws_instance",
                            "name": "a",
                            "values": {
                                "id": "i-000000000000aaaa1",
                                "user_note": "peer is i-000000000000bbbb2",
                            },
                        },
                        {
                            "address": "aws_instance.b",
                            "type": "aws_instance",
                            "name": "b",
                            "values": {
                                "id": "i-000000000000bbbb2",
                                "user_note": "peer is i-000000000000aaaa1",
                            },
                        },
                    ]
                }
            }
        }
        result = import_terraform(data)
        pairs = _edge_pairs(result)
        assert len(pairs) == 1  # one direction kept, the reverse dropped
        assert len(result.warnings) == 1
        assert "cycle" in result.warnings[0]
        # the emitted graph must satisfy the loader's DAG requirement
        load_yaml_ok(result)

    def test_ambiguous_identity_strings_do_not_link(self):
        shared = "shared.example.internal.host"
        data = {
            "values": {
                "root_module": {
                    "resources": [
                        {
                            "address": "aws_instance.a",
                            "type": "aws_instance",
                            "name": "a",
                            "values": {"id": "i-00000000000aaaa11", "endpoint": shared},
                        },
                        {
                            "address": "aws_instance.b",
                            "type": "aws_instance",
                            "name": "b",
                            "values": {"id": "i-00000000000bbbb22", "endpoint": shared},
                        },
                        {
                            "address": "aws_instance.c",
                            "type": "aws_instance",
                            "name": "c",
                            "values": {"id": "i-00000000000cccc33", "note": shared},
                        },
                    ]
                }
            }
        }
        result = import_terraform(data)
        assert result.edges == []

    def test_unrecognised_input_raises(self):
        with pytest.raises(ValueError, match="Unrecognised input"):
            import_terraform({"hello": "world"})


def load_yaml_ok(result):
    """Write the YAML and load it back through the strict model loader."""
    import tempfile

    with tempfile.NamedTemporaryFile(
        "w", suffix=".yaml", delete=False, encoding="utf-8"
    ) as fh:
        fh.write(topology_yaml(result))
        path = Path(fh.name)
    try:
        return load_yaml(path)
    finally:
        path.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# YAML output / simulate connectivity
# ---------------------------------------------------------------------------


class TestYamlOutput:
    def test_round_trip_through_loader(self, sample_result):
        graph = load_yaml_ok(sample_result)
        assert len(graph.components) == len(sample_result.graph.components)
        assert len(graph.all_dependency_edges()) == len(sample_result.edges)

    def test_yaml_contains_schema_version_and_evidence_header(self, sample_result):
        text = topology_yaml(sample_result)
        assert "schema_version" in text
        assert "# Edge evidence:" in text
        assert "load balancer wiring" in text

    def test_loaded_graph_is_simulatable(self, sample_result):
        graph = load_yaml_ok(sample_result)
        score = graph.resilience_score()
        assert 0.0 <= score <= 100.0


# ---------------------------------------------------------------------------
# CLI contract
# ---------------------------------------------------------------------------


def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "faultray", "import", "terraform", *args],
        capture_output=True,
        text=True,
        timeout=120,
    )


class TestCli:
    def test_import_writes_yaml_and_exits_zero(self, tmp_path):
        out = tmp_path / "topo.yaml"
        proc = _run_cli(str(SAMPLE_STATE), "-o", str(out))
        assert proc.returncode == 0, proc.stderr or proc.stdout
        assert out.exists()
        graph = load_yaml(out)
        assert len(graph.components) == 11

    def test_refuses_overwrite_without_force(self, tmp_path):
        out = tmp_path / "topo.yaml"
        out.write_text("existing")
        proc = _run_cli(str(SAMPLE_STATE), "-o", str(out))
        assert proc.returncode == 1
        assert out.read_text() == "existing"
        proc2 = _run_cli(str(SAMPLE_STATE), "-o", str(out), "--force")
        assert proc2.returncode == 0

    def test_json_summary(self, tmp_path):
        out = tmp_path / "topo.yaml"
        proc = _run_cli(str(SAMPLE_STATE), "-o", str(out), "--json")
        assert proc.returncode == 0, proc.stderr or proc.stdout
        payload = json.loads(proc.stdout[proc.stdout.index("{"):])
        assert payload["components"] == 11
        assert payload["dependencies"] == 11
        assert payload["isolated_components"] == []
        assert payload["component_types"]["external_api"] == 2

    def test_missing_file_exits_one(self, tmp_path):
        proc = _run_cli(str(tmp_path / "nope.json"))
        assert proc.returncode == 1

    def test_non_terraform_json_exits_one(self, tmp_path):
        bad = tmp_path / "bad.json"
        bad.write_text('{"foo": 1}')
        proc = _run_cli(str(bad))
        assert proc.returncode == 1
