"""Tests for Terraform integration (discovery/terraform.py)."""

from __future__ import annotations

import json

import pytest

from faultray.discovery.terraform import (
    TF_RESOURCE_MAP,
    _assess_change_risk,
    _diff_attributes,
    _extract_replicas,
    _resource_to_component,
    parse_tf_plan,
    parse_tf_state,
    load_tf_state_file,
)
from faultray.model.components import ComponentType


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

def _make_state(*resources):
    """Build a minimal terraform show -json state dict."""
    return {
        "values": {
            "root_module": {
                "resources": list(resources),
            },
        },
    }


def _make_resource(
    res_type: str,
    name: str = "test",
    values: dict | None = None,
    address: str | None = None,
):
    """Build a single resource block for terraform state."""
    return {
        "type": res_type,
        "name": name,
        "address": address or f"{res_type}.{name}",
        "values": values or {},
    }


def _make_plan_change(
    res_type: str,
    name: str,
    actions: list[str],
    before: dict | None = None,
    after: dict | None = None,
):
    """Build a single resource_change entry for a terraform plan."""
    return {
        "type": res_type,
        "name": name,
        "address": f"{res_type}.{name}",
        "change": {
            "actions": actions,
            "before": before,
            "after": after,
        },
    }


# ===================================================================
# parse_tf_state
# ===================================================================


class TestParseTfState:
    """Tests for parse_tf_state()."""

    def test_empty_state(self):
        graph = parse_tf_state({})
        assert len(graph.components) == 0

    def test_empty_root_module(self):
        graph = parse_tf_state({"values": {"root_module": {"resources": []}}})
        assert len(graph.components) == 0

    def test_aws_instance(self):
        state = _make_state(
            _make_resource("aws_instance", "web", {
                "instance_type": "t3.large",
                "private_ip": "10.0.1.5",
                "tags": {"Name": "web-server"},
            }),
        )
        graph = parse_tf_state(state)

        assert len(graph.components) == 1
        comp = graph.get_component("aws_instance.web")
        assert comp is not None
        assert comp.type == ComponentType.APP_SERVER
        assert comp.name == "web-server"
        assert comp.host == "10.0.1.5"
        assert comp.parameters["terraform_type"] == "aws_instance"

    def test_aws_db_instance(self):
        state = _make_state(
            _make_resource("aws_db_instance", "main_db", {
                "instance_class": "db.r5.xlarge",
                "endpoint": "mydb.cluster.rds.amazonaws.com",
                "allocated_storage": 100,
                "multi_az": True,
                "tags": {"Name": "main-db"},
            }),
        )
        graph = parse_tf_state(state)

        comp = graph.get_component("aws_db_instance.main_db")
        assert comp is not None
        assert comp.type == ComponentType.DATABASE
        assert comp.replicas == 2  # multi_az => 2
        assert comp.port == 3306  # default for aws_db_instance
        assert comp.capacity.max_disk_gb == 100.0

    def test_aws_elasticache_cluster(self):
        state = _make_state(
            _make_resource("aws_elasticache_cluster", "redis", {
                "num_cache_nodes": 3,
                "port": 6379,
            }),
        )
        graph = parse_tf_state(state)

        comp = graph.get_component("aws_elasticache_cluster.redis")
        assert comp is not None
        assert comp.type == ComponentType.CACHE
        assert comp.replicas == 3
        assert comp.port == 6379

    def test_aws_lb(self):
        state = _make_state(
            _make_resource("aws_lb", "alb", {
                "name": "front-alb",
            }),
        )
        graph = parse_tf_state(state)

        comp = graph.get_component("aws_lb.alb")
        assert comp is not None
        assert comp.type == ComponentType.LOAD_BALANCER
        assert comp.port == 443  # default for aws_lb

    def test_multiple_resources_with_dependency_inference(self):
        state = _make_state(
            _make_resource("aws_lb", "alb", {"name": "alb"}),
            _make_resource("aws_instance", "app", {"name": "app"}),
            _make_resource("aws_db_instance", "db", {"name": "db"}),
        )
        graph = parse_tf_state(state)

        assert len(graph.components) == 3

        # LB -> APP_SERVER dependency should be inferred
        alb_deps = graph.get_dependencies("aws_lb.alb")
        dep_types = [d.type for d in alb_deps]
        assert ComponentType.APP_SERVER in dep_types

        # APP_SERVER -> DATABASE dependency should be inferred
        app_deps = graph.get_dependencies("aws_instance.app")
        dep_types = [d.type for d in app_deps]
        assert ComponentType.DATABASE in dep_types

    def test_unknown_resource_type_skipped(self):
        state = _make_state(
            _make_resource("aws_iam_role", "admin", {"name": "admin"}),
        )
        graph = parse_tf_state(state)
        assert len(graph.components) == 0

    def test_child_modules(self):
        state = {
            "values": {
                "root_module": {
                    "resources": [],
                    "child_modules": [
                        {
                            "resources": [
                                _make_resource("aws_instance", "child_app", {
                                    "name": "child-app",
                                }),
                            ],
                        },
                    ],
                },
            },
        }
        graph = parse_tf_state(state)
        assert len(graph.components) == 1

    def test_tfstate_v4_format(self):
        """terraform.tfstate format (version 4) with instances."""
        state = {
            "resources": [
                {
                    "type": "aws_instance",
                    "name": "web",
                    "instances": [
                        {
                            "attributes": {
                                "private_ip": "10.0.0.1",
                                "instance_type": "t3.micro",
                            },
                        },
                    ],
                },
            ],
        }
        graph = parse_tf_state(state)
        assert len(graph.components) == 1
        comp = graph.get_component("aws_instance.web")
        assert comp is not None
        assert comp.type == ComponentType.APP_SERVER

    def test_tags_extracted_into_component(self):
        state = _make_state(
            _make_resource("aws_instance", "tagged", {
                "tags": {"Name": "tagged-srv", "Env": "prod"},
            }),
        )
        graph = parse_tf_state(state)
        comp = graph.get_component("aws_instance.tagged")
        assert "Name" in comp.tags
        assert "Env" in comp.tags

    def test_desired_count_replicas(self):
        state = _make_state(
            _make_resource("aws_ecs_service", "api", {
                "desired_count": 5,
                "name": "api-svc",
            }),
        )
        graph = parse_tf_state(state)
        comp = graph.get_component("aws_ecs_service.api")
        assert comp.replicas == 5


# ===================================================================
# parse_tf_plan
# ===================================================================


class TestParseTfPlan:
    """Tests for parse_tf_plan()."""

    def test_empty_plan(self):
        result = parse_tf_plan({})
        assert result["changes"] == []

    def test_create_action(self):
        plan = {
            "resource_changes": [
                _make_plan_change(
                    "aws_instance", "new_app",
                    actions=["create"],
                    before=None,
                    after={"instance_type": "t3.medium", "name": "new-app"},
                ),
            ],
        }
        result = parse_tf_plan(plan)

        assert len(result["changes"]) == 1
        change = result["changes"][0]
        assert "create" in change["actions"]
        assert change["address"] == "aws_instance.new_app"

        # After graph should contain the new component
        after_graph = result["after"]
        assert "aws_instance.new_app" in after_graph.components

    def test_delete_action(self):
        plan = {
            "resource_changes": [
                _make_plan_change(
                    "aws_instance", "old_app",
                    actions=["delete"],
                    before={"instance_type": "t3.small", "name": "old-app"},
                    after=None,
                ),
            ],
        }
        result = parse_tf_plan(plan)

        assert len(result["changes"]) == 1
        change = result["changes"][0]
        assert "delete" in change["actions"]
        assert change["risk_level"] >= 8

    def test_modify_action(self):
        plan = {
            "resource_changes": [
                _make_plan_change(
                    "aws_instance", "app",
                    actions=["update"],
                    before={"instance_type": "t3.small", "name": "app"},
                    after={"instance_type": "t3.large", "name": "app"},
                ),
            ],
        }
        result = parse_tf_plan(plan)

        assert len(result["changes"]) == 1
        change = result["changes"][0]
        # Instance type change => risk >= 6
        assert change["risk_level"] >= 6
        attr_changes = change["changed_attributes"]
        changed_keys = [a["attribute"] for a in attr_changes]
        assert "instance_type" in changed_keys

    def test_delete_db_highest_risk(self):
        plan = {
            "resource_changes": [
                _make_plan_change(
                    "aws_db_instance", "critical_db",
                    actions=["delete"],
                    before={"instance_class": "db.r5.xlarge", "name": "critical-db"},
                    after=None,
                ),
            ],
        }
        result = parse_tf_plan(plan)
        assert result["changes"][0]["risk_level"] == 10

    def test_noop_skipped(self):
        plan = {
            "resource_changes": [
                _make_plan_change(
                    "aws_instance", "stable",
                    actions=["no-op"],
                    before={"name": "stable"},
                    after={"name": "stable"},
                ),
            ],
        }
        result = parse_tf_plan(plan)
        assert len(result["changes"]) == 0

    def test_read_action_skipped(self):
        plan = {
            "resource_changes": [
                _make_plan_change(
                    "aws_instance", "data",
                    actions=["read"],
                    before={"name": "data"},
                    after={"name": "data"},
                ),
            ],
        }
        result = parse_tf_plan(plan)
        assert len(result["changes"]) == 0

    def test_changes_sorted_by_risk_descending(self):
        plan = {
            "resource_changes": [
                _make_plan_change(
                    "aws_instance", "low_risk",
                    actions=["update"],
                    before={"name": "a"},
                    after={"name": "b"},
                ),
                _make_plan_change(
                    "aws_db_instance", "high_risk",
                    actions=["delete"],
                    before={"name": "db"},
                    after=None,
                ),
            ],
        }
        result = parse_tf_plan(plan)
        risks = [c["risk_level"] for c in result["changes"]]
        assert risks == sorted(risks, reverse=True)


# ===================================================================
# _assess_change_risk
# ===================================================================


class TestAssessChangeRisk:
    """Tests for _assess_change_risk()."""

    def test_delete_base_risk(self):
        risk = _assess_change_risk("aws_instance", ["delete"], {}, {})
        assert risk >= 8

    def test_create_delete_replace_risk(self):
        risk = _assess_change_risk("aws_instance", ["create", "delete"], {}, {})
        assert risk >= 9

    def test_db_delete_max_risk(self):
        risk = _assess_change_risk("aws_db_instance", ["delete"], {}, {})
        assert risk == 10

    def test_instance_type_change_risk(self):
        risk = _assess_change_risk(
            "aws_instance", ["update"],
            {"instance_type": "t3.small"},
            {"instance_type": "t3.large"},
        )
        assert risk >= 6

    def test_instance_class_change_risk(self):
        risk = _assess_change_risk(
            "aws_db_instance", ["update"],
            {"instance_class": "db.r5.large"},
            {"instance_class": "db.r5.xlarge"},
        )
        assert risk >= 7

    def test_scaling_down_risk(self):
        risk = _assess_change_risk(
            "aws_ecs_service", ["update"],
            {"desired_count": 5},
            {"desired_count": 2},
        )
        assert risk >= 5

    def test_capacity_reduction_risk(self):
        risk = _assess_change_risk(
            "aws_db_instance", ["update"],
            {"allocated_storage": 200},
            {"allocated_storage": 100},
        )
        assert risk >= 7

    def test_no_change_minimal_risk(self):
        risk = _assess_change_risk(
            "aws_s3_bucket", ["update"],
            {"name": "bucket"},
            {"name": "bucket-renamed"},
        )
        assert risk >= 1

    def test_security_group_change(self):
        risk = _assess_change_risk("aws_security_group", ["update"], {}, {})
        assert risk >= 5


# ===================================================================
# _diff_attributes
# ===================================================================


class TestDiffAttributes:
    """Tests for _diff_attributes()."""

    def test_no_changes(self):
        result = _diff_attributes({"a": 1}, {"a": 1})
        assert result == []

    def test_value_changed(self):
        result = _diff_attributes({"size": 10}, {"size": 20})
        assert len(result) == 1
        assert result[0]["attribute"] == "size"
        assert result[0]["before"] == 10
        assert result[0]["after"] == 20

    def test_new_key(self):
        result = _diff_attributes({}, {"new_key": "val"})
        assert len(result) == 1
        assert result[0]["attribute"] == "new_key"
        assert result[0]["before"] is None

    def test_removed_key(self):
        result = _diff_attributes({"old": "val"}, {})
        assert len(result) == 1
        assert result[0]["after"] is None

    def test_skips_noisy_keys(self):
        result = _diff_attributes(
            {"tags": {"a": 1}, "arn": "old", "id": "old"},
            {"tags": {"a": 2}, "arn": "new", "id": "new"},
        )
        assert all(r["attribute"] not in ("tags", "arn", "id") for r in result)


# ===================================================================
# _extract_replicas
# ===================================================================


class TestExtractReplicas:
    """Tests for _extract_replicas()."""

    def test_desired_count(self):
        assert _extract_replicas("aws_ecs_service", {"desired_count": 4}) == 4

    def test_num_cache_nodes(self):
        assert _extract_replicas("aws_elasticache_cluster", {"num_cache_nodes": 3}) == 3

    def test_multi_az(self):
        assert _extract_replicas("aws_db_instance", {"multi_az": True}) == 2

    def test_desired_capacity(self):
        assert _extract_replicas("aws_autoscaling_group", {"desired_capacity": 6}) == 6

    def test_default(self):
        assert _extract_replicas("aws_instance", {}) == 1

    def test_zero_desired_count_clamps_to_one(self):
        assert _extract_replicas("aws_ecs_service", {"desired_count": 0}) == 1


# ===================================================================
# _resource_to_component
# ===================================================================


class TestResourceToComponent:
    """Tests for _resource_to_component()."""

    def test_unknown_type_returns_none(self):
        res = {"type": "aws_iam_policy", "name": "pol", "values": {}}
        assert _resource_to_component(res) is None

    def test_maps_all_known_aws_types(self):
        for tf_type, comp_type in TF_RESOURCE_MAP.items():
            res = {"type": tf_type, "name": "x", "values": {"name": "x"}}
            comp = _resource_to_component(res)
            assert comp is not None, f"Failed for {tf_type}"
            assert comp.type == comp_type, f"Wrong type for {tf_type}"


# ===================================================================
# load_tf_state_file
# ===================================================================


class TestLoadTfStateFile:
    """Tests for load_tf_state_file()."""

    def test_load_from_file(self, tmp_path):
        state = _make_state(
            _make_resource("aws_instance", "file_test", {"name": "from-file"}),
        )
        tf_file = tmp_path / "terraform.tfstate"
        tf_file.write_text(json.dumps(state))

        graph = load_tf_state_file(tf_file)
        assert len(graph.components) == 1
        assert "aws_instance.file_test" in graph.components


# ===================================================================
# Dependency inference
# ===================================================================


class TestDependencyInference:
    """Tests for _infer_dependencies() via parse_tf_state()."""

    def test_lb_to_app_dependency(self):
        state = _make_state(
            _make_resource("aws_lb", "lb", {"name": "lb"}),
            _make_resource("aws_instance", "app", {"name": "app"}),
        )
        graph = parse_tf_state(state)

        deps = graph.get_dependencies("aws_lb.lb")
        assert any(d.type == ComponentType.APP_SERVER for d in deps)

    def test_app_to_db_dependency(self):
        state = _make_state(
            _make_resource("aws_instance", "app", {"name": "app"}),
            _make_resource("aws_db_instance", "db", {"name": "db"}),
        )
        graph = parse_tf_state(state)

        deps = graph.get_dependencies("aws_instance.app")
        assert any(d.type == ComponentType.DATABASE for d in deps)

    def test_app_to_cache_dependency(self):
        state = _make_state(
            _make_resource("aws_instance", "app", {"name": "app"}),
            _make_resource("aws_elasticache_cluster", "redis", {"name": "redis"}),
        )
        graph = parse_tf_state(state)

        deps = graph.get_dependencies("aws_instance.app")
        assert any(d.type == ComponentType.CACHE for d in deps)

    def test_explicit_reference_in_values(self):
        state = _make_state(
            _make_resource("aws_instance", "app", {
                "name": "app",
                "subnet_ref": "references aws_db_instance.db",
            }),
            _make_resource("aws_db_instance", "db", {"name": "db"}),
        )
        graph = parse_tf_state(state)

        edge = graph.get_dependency_edge("aws_instance.app", "aws_db_instance.db")
        # Should exist from either inferred rules or explicit reference
        assert edge is not None
