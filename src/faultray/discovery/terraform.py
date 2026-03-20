# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Business Source License 1.1. See LICENSE file for details.

"""Terraform integration - import infrastructure from Terraform state/plan."""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

from faultray.model.components import (
    Capacity,
    Component,
    ComponentType,
    Dependency,
    ResourceMetrics,
)
from faultray.model.graph import InfraGraph

# Terraform resource type to FaultRay component type mapping
TF_RESOURCE_MAP: dict[str, ComponentType] = {
    # AWS
    "aws_lb": ComponentType.LOAD_BALANCER,
    "aws_alb": ComponentType.LOAD_BALANCER,
    "aws_elb": ComponentType.LOAD_BALANCER,
    "aws_instance": ComponentType.APP_SERVER,
    "aws_ecs_service": ComponentType.APP_SERVER,
    "aws_ecs_task_definition": ComponentType.APP_SERVER,
    "aws_lambda_function": ComponentType.APP_SERVER,
    "aws_eks_cluster": ComponentType.APP_SERVER,
    "aws_db_instance": ComponentType.DATABASE,
    "aws_rds_cluster": ComponentType.DATABASE,
    "aws_dynamodb_table": ComponentType.DATABASE,
    "aws_elasticache_cluster": ComponentType.CACHE,
    "aws_elasticache_replication_group": ComponentType.CACHE,
    "aws_sqs_queue": ComponentType.QUEUE,
    "aws_mq_broker": ComponentType.QUEUE,
    "aws_s3_bucket": ComponentType.STORAGE,
    "aws_efs_file_system": ComponentType.STORAGE,
    "aws_route53_record": ComponentType.DNS,
    "aws_cloudfront_distribution": ComponentType.LOAD_BALANCER,
    # GCP
    "google_compute_instance": ComponentType.APP_SERVER,
    "google_cloud_run_service": ComponentType.APP_SERVER,
    "google_sql_database_instance": ComponentType.DATABASE,
    "google_redis_instance": ComponentType.CACHE,
    "google_pubsub_topic": ComponentType.QUEUE,
    "google_storage_bucket": ComponentType.STORAGE,
    "google_compute_forwarding_rule": ComponentType.LOAD_BALANCER,
    # Azure
    "azurerm_virtual_machine": ComponentType.APP_SERVER,
    "azurerm_linux_virtual_machine": ComponentType.APP_SERVER,
    "azurerm_container_group": ComponentType.APP_SERVER,
    "azurerm_mssql_server": ComponentType.DATABASE,
    "azurerm_postgresql_server": ComponentType.DATABASE,
    "azurerm_redis_cache": ComponentType.CACHE,
    "azurerm_servicebus_queue": ComponentType.QUEUE,
    "azurerm_storage_account": ComponentType.STORAGE,
    "azurerm_lb": ComponentType.LOAD_BALANCER,
}

# Default capacity by component type
DEFAULT_CAPACITY: dict[ComponentType, Capacity] = {
    ComponentType.LOAD_BALANCER: Capacity(max_connections=50000, max_rps=100000),
    ComponentType.APP_SERVER: Capacity(max_connections=1000, connection_pool_size=200, timeout_seconds=30),
    ComponentType.DATABASE: Capacity(max_connections=200, max_disk_gb=500, timeout_seconds=60),
    ComponentType.CACHE: Capacity(max_connections=10000, timeout_seconds=5),
    ComponentType.QUEUE: Capacity(max_connections=5000),
    ComponentType.STORAGE: Capacity(max_disk_gb=1000),
    ComponentType.DNS: Capacity(max_rps=100000),
}


def parse_tf_state(state_json: dict) -> InfraGraph:
    """Parse terraform show -json output into an InfraGraph."""
    graph = InfraGraph()

    resources = _extract_resources(state_json)

    # Create components from resources
    for res in resources:
        comp = _resource_to_component(res)
        if comp:
            graph.add_component(comp)

    # Infer dependencies from resource references
    _infer_dependencies(graph, resources)

    return graph


def parse_tf_plan(plan_json: dict) -> dict:
    """Parse terraform plan -json output and identify changes with risk analysis.

    Returns a dict with:
    - 'before': InfraGraph of current state
    - 'after': InfraGraph of planned state
    - 'changes': list of resource changes with risk assessment
    """
    changes = []
    before_resources = []
    after_resources = []

    for change in plan_json.get("resource_changes", []):
        action = change.get("change", {}).get("actions", [])
        resource_type = change.get("type", "")
        resource_name = change.get("name", "")
        address = change.get("address", "")

        before_vals = change.get("change", {}).get("before") or {}
        after_vals = change.get("change", {}).get("after") or {}

        # Track before/after resources for graph building
        if before_vals and "no-op" not in action:
            before_resources.append({
                "type": resource_type,
                "name": resource_name,
                "address": address,
                "values": before_vals,
            })
        if after_vals:
            after_resources.append({
                "type": resource_type,
                "name": resource_name,
                "address": address,
                "values": after_vals,
            })

        if "no-op" in action or "read" in action:
            continue

        # Analyze the change
        change_info = {
            "address": address,
            "type": resource_type,
            "name": resource_name,
            "actions": action,
            "risk_level": _assess_change_risk(resource_type, action, before_vals, after_vals),
            "changed_attributes": _diff_attributes(before_vals, after_vals),
        }
        changes.append(change_info)

    # Build before/after graphs
    before_graph = InfraGraph()
    for res in before_resources:
        comp = _resource_to_component(res)
        if comp:
            before_graph.add_component(comp)
    _infer_dependencies(before_graph, before_resources)

    after_graph = InfraGraph()
    for res in after_resources:
        comp = _resource_to_component(res)
        if comp:
            after_graph.add_component(comp)
    _infer_dependencies(after_graph, after_resources)

    return {
        "before": before_graph,
        "after": after_graph,
        "changes": sorted(changes, key=lambda c: c["risk_level"], reverse=True),
    }


def load_tf_state_file(path: Path) -> InfraGraph:
    """Load from a terraform.tfstate file directly."""
    data = json.loads(path.read_text())
    return parse_tf_state(data)


def load_tf_state_cmd(tf_dir: Path | None = None) -> InfraGraph:
    """Run 'terraform show -json' and parse the output."""
    cmd = ["terraform", "show", "-json"]
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=tf_dir,
    )
    if result.returncode != 0:
        raise RuntimeError(f"terraform show failed: {result.stderr}")

    data = json.loads(result.stdout)
    return parse_tf_state(data)


def load_tf_plan_cmd(plan_file: Path | None = None, tf_dir: Path | None = None) -> dict:
    """Run 'terraform show -json <planfile>' and parse the output."""
    cmd = ["terraform", "show", "-json"]
    if plan_file:
        cmd.append(str(plan_file))

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=tf_dir,
    )
    if result.returncode != 0:
        raise RuntimeError(f"terraform show failed: {result.stderr}")

    data = json.loads(result.stdout)
    return parse_tf_plan(data)


def load_hcl_directory(tf_dir: Path) -> InfraGraph:
    """Parse .tf files directly from a Terraform project directory.

    Scans for resource blocks (aws_instance, aws_rds_cluster, etc.)
    and maps them to InfraGraph components.  This provides a best-effort
    import when no tfstate is available — only resource type and name are
    extracted (attribute values are not deeply parsed from HCL).
    """
    graph = InfraGraph()

    # HCL resource type to ComponentType mapping (subset most commonly used)
    hcl_type_map: dict[str, ComponentType] = {
        "aws_instance": ComponentType.APP_SERVER,
        "aws_ecs_service": ComponentType.APP_SERVER,
        "aws_rds_cluster": ComponentType.DATABASE,
        "aws_rds_instance": ComponentType.DATABASE,
        "aws_elasticache_cluster": ComponentType.CACHE,
        "aws_lb": ComponentType.LOAD_BALANCER,
        "aws_alb": ComponentType.LOAD_BALANCER,
        "aws_sqs_queue": ComponentType.QUEUE,
        "aws_s3_bucket": ComponentType.STORAGE,
        "aws_route53_zone": ComponentType.DNS,
    }

    # Regex to match top-level resource blocks: resource "type" "name" { ... }
    resource_re = re.compile(
        r'resource\s+"([^"]+)"\s+"([^"]+)"\s*\{',
    )

    tf_files = sorted(tf_dir.glob("*.tf"))
    resources: list[dict] = []

    for tf_file in tf_files:
        content = tf_file.read_text(encoding="utf-8", errors="replace")
        for match in resource_re.finditer(content):
            res_type = match.group(1)
            res_name = match.group(2)

            comp_type = hcl_type_map.get(res_type)
            if comp_type is None:
                # Also fall back to the broader TF_RESOURCE_MAP
                comp_type = TF_RESOURCE_MAP.get(res_type)
            if comp_type is None:
                continue

            address = f"{res_type}.{res_name}"
            capacity = DEFAULT_CAPACITY.get(comp_type, Capacity())

            comp = Component(
                id=address,
                name=res_name,
                type=comp_type,
                capacity=capacity,
                parameters={
                    "terraform_type": res_type,
                    "terraform_address": address,
                    "source": "hcl_parse",
                },
            )
            graph.add_component(comp)
            resources.append({
                "type": res_type,
                "name": res_name,
                "address": address,
                "values": {},
            })

    # Infer dependencies using the same heuristic as tfstate import
    _infer_dependencies(graph, resources)

    return graph


# --- Internal helpers ---


def _extract_resources(state_json: dict) -> list[dict]:
    """Extract flat list of resources from terraform state JSON."""
    resources = []

    # Handle terraform show -json format
    values = state_json.get("values", {})
    root_module = values.get("root_module", {})

    for res in root_module.get("resources", []):
        resources.append({
            "type": res.get("type", ""),
            "name": res.get("name", ""),
            "address": res.get("address", ""),
            "values": res.get("values", {}),
        })

    # Handle child modules
    for child in root_module.get("child_modules", []):
        for res in child.get("resources", []):
            resources.append({
                "type": res.get("type", ""),
                "name": res.get("name", ""),
                "address": res.get("address", ""),
                "values": res.get("values", {}),
            })

    # Handle terraform.tfstate format (version 4)
    if not resources and "resources" in state_json:
        for res_block in state_json["resources"]:
            res_type = res_block.get("type", "")
            res_name = res_block.get("name", "")
            for instance in res_block.get("instances", []):
                attrs = instance.get("attributes", {})
                resources.append({
                    "type": res_type,
                    "name": res_name,
                    "address": f"{res_type}.{res_name}",
                    "values": attrs,
                })

    return resources


def _resource_to_component(res: dict) -> Component | None:
    """Convert a Terraform resource to a FaultRay Component."""
    res_type = res["type"]
    comp_type = TF_RESOURCE_MAP.get(res_type)
    if not comp_type:
        return None

    address = res.get("address", f"{res_type}.{res['name']}")
    values = res.get("values", {})

    # Extract useful attributes
    name = values.get("tags", {}).get("Name", "") if isinstance(values.get("tags"), dict) else ""
    if not name:
        name = values.get("name", res["name"])

    host = values.get("private_ip", values.get("endpoint", values.get("address", "")))
    port = _extract_port(res_type, values)
    replicas = _extract_replicas(res_type, values)

    # Build capacity from resource attributes
    capacity = _extract_capacity(res_type, values, comp_type)

    # Build metrics from resource attributes (what we can infer)
    metrics = _extract_metrics(res_type, values)

    return Component(
        id=address,
        name=name or address,
        type=comp_type,
        host=str(host) if host else "",
        port=port,
        replicas=replicas,
        capacity=capacity,
        metrics=metrics,
        parameters={
            "terraform_type": res_type,
            "terraform_address": address,
        },
        tags=list(values.get("tags", {}).keys()) if isinstance(values.get("tags"), dict) else [],
    )


def _extract_port(res_type: str, values: dict) -> int:
    """Extract port from resource attributes."""
    if "port" in values:
        return int(values["port"])

    port_map = {
        "aws_db_instance": 3306,
        "aws_rds_cluster": 5432,
        "aws_elasticache_cluster": 6379,
        "aws_sqs_queue": 443,
        "aws_lb": 443,
        "aws_alb": 443,
        "google_sql_database_instance": 5432,
        "google_redis_instance": 6379,
        "azurerm_postgresql_server": 5432,
        "azurerm_redis_cache": 6380,
    }
    return port_map.get(res_type, 0)


def _extract_replicas(res_type: str, values: dict) -> int:
    """Extract replica count from resource attributes."""
    # ECS desired count
    if "desired_count" in values:
        return max(1, int(values["desired_count"]))

    # Elasticache num_cache_nodes
    if "num_cache_nodes" in values:
        return max(1, int(values["num_cache_nodes"]))

    # RDS multi-az
    if values.get("multi_az"):
        return 2

    # ASG
    if "desired_capacity" in values:
        return max(1, int(values["desired_capacity"]))

    return 1


def _extract_capacity(res_type: str, values: dict, comp_type: ComponentType) -> Capacity:
    """Extract capacity from resource attributes."""
    base = DEFAULT_CAPACITY.get(comp_type, Capacity())

    # RDS max connections (based on instance class)
    if "allocated_storage" in values:
        base.max_disk_gb = float(values["allocated_storage"])

    # Instance type to connection estimate
    instance_class = values.get("instance_class", values.get("instance_type", ""))
    if instance_class:
        base.max_connections = _estimate_connections(instance_class, comp_type)

    return base


def _estimate_connections(instance_class: str, comp_type: ComponentType) -> int:
    """Estimate max connections based on instance class."""
    # Rough mapping based on instance size
    size_map = {
        "micro": 50, "small": 100, "medium": 200,
        "large": 500, "xlarge": 1000, "2xlarge": 2000,
        "4xlarge": 5000, "8xlarge": 10000,
    }
    for size, conns in size_map.items():
        if size in instance_class.lower():
            if comp_type == ComponentType.DATABASE:
                return conns
            return conns * 2
    return 500


def _extract_metrics(res_type: str, values: dict) -> ResourceMetrics:
    """Extract what metrics we can from Terraform attributes."""
    metrics = ResourceMetrics()

    # Disk usage estimate from allocated storage
    if "allocated_storage" in values:
        metrics.disk_total_gb = float(values["allocated_storage"])

    return metrics


def _infer_dependencies(graph: InfraGraph, resources: list[dict]) -> None:
    """Infer dependencies between components based on resource references."""
    component_ids = set(graph.components.keys())

    # Build a map of resource type -> component IDs for matching
    type_to_ids: dict[str, list[str]] = {}
    for comp_id, comp in graph.components.items():
        tf_type = comp.parameters.get("terraform_type", "")
        if tf_type:
            type_to_ids.setdefault(tf_type, []).append(comp_id)

    # Common dependency patterns
    dependency_rules = [
        # LB -> App servers
        (ComponentType.LOAD_BALANCER, ComponentType.APP_SERVER, "requires", 1.0),
        # App servers -> Database
        (ComponentType.APP_SERVER, ComponentType.DATABASE, "requires", 1.0),
        # App servers -> Cache
        (ComponentType.APP_SERVER, ComponentType.CACHE, "optional", 0.7),
        # App servers -> Queue
        (ComponentType.APP_SERVER, ComponentType.QUEUE, "async", 0.5),
        # App servers -> Storage
        (ComponentType.APP_SERVER, ComponentType.STORAGE, "optional", 0.3),
        # DNS -> LB
        (ComponentType.DNS, ComponentType.LOAD_BALANCER, "requires", 1.0),
    ]

    # Auto-infer dependencies based on component types
    for source_type, target_type, dep_type, weight in dependency_rules:
        sources = [c for c in graph.components.values() if c.type == source_type]
        targets = [c for c in graph.components.values() if c.type == target_type]

        for source in sources:
            for target in targets:
                if source.id != target.id:
                    graph.add_dependency(Dependency(
                        source_id=source.id,
                        target_id=target.id,
                        dependency_type=dep_type,
                        weight=weight,
                    ))

    # Also try to find explicit references in resource values
    for res in resources:
        address = res.get("address", "")
        if address not in component_ids:
            continue

        values = res.get("values", {})
        _find_references_in_values(graph, address, values, component_ids)


def _find_references_in_values(
    graph: InfraGraph, source_id: str, values: dict, component_ids: set[str]
) -> None:
    """Recursively search resource values for references to other components."""
    if not isinstance(values, dict):
        return

    for key, val in values.items():
        if isinstance(val, str):
            # Check if any component ID appears in the value
            for comp_id in component_ids:
                if comp_id != source_id and comp_id in val:
                    # Avoid duplicate edges
                    existing = graph.get_dependency_edge(source_id, comp_id)
                    if not existing:
                        graph.add_dependency(Dependency(
                            source_id=source_id,
                            target_id=comp_id,
                            dependency_type="requires",
                            weight=0.8,
                        ))
        elif isinstance(val, dict):
            _find_references_in_values(graph, source_id, val, component_ids)
        elif isinstance(val, list):
            for item in val:
                if isinstance(item, dict):
                    _find_references_in_values(graph, source_id, item, component_ids)


def _assess_change_risk(
    resource_type: str,
    actions: list[str],
    before: dict,
    after: dict,
) -> int:
    """Assess risk level of a Terraform change (1-10)."""
    risk = 1

    # Destructive actions are highest risk
    if "delete" in actions:
        risk = max(risk, 8)
    if "create" in actions and "delete" in actions:  # replace
        risk = max(risk, 9)

    # Database changes are high risk
    if resource_type in ("aws_db_instance", "aws_rds_cluster", "google_sql_database_instance"):
        risk = max(risk, 6)
        if "delete" in actions:
            risk = 10

    # Security group changes
    if resource_type in ("aws_security_group", "aws_security_group_rule"):
        risk = max(risk, 5)

    # Instance type changes (potential downtime)
    if before.get("instance_type") != after.get("instance_type"):
        risk = max(risk, 6)
    if before.get("instance_class") != after.get("instance_class"):
        risk = max(risk, 7)

    # Scaling changes
    if before.get("desired_count") != after.get("desired_count"):
        old = before.get("desired_count", 0) or 0
        new = after.get("desired_count", 0) or 0
        if new < old:  # scaling down
            risk = max(risk, 5)

    # Connection/capacity changes
    for key in ("allocated_storage", "max_connections", "num_cache_nodes"):
        old_val = before.get(key)
        new_val = after.get(key)
        if old_val is not None and new_val is not None:
            if float(new_val) < float(old_val):
                risk = max(risk, 7)  # reducing capacity

    return min(10, risk)


def _diff_attributes(before: dict, after: dict) -> list[dict]:
    """Find changed attributes between before and after state."""
    changes = []
    all_keys = before.keys() | after.keys()

    # Skip noisy attributes
    skip_keys = {"tags", "tags_all", "arn", "id", "self_link", "timeouts"}

    for key in sorted(all_keys):
        if key in skip_keys:
            continue
        old_val = before.get(key)
        new_val = after.get(key)
        if old_val != new_val:
            changes.append({
                "attribute": key,
                "before": old_val,
                "after": new_val,
            })

    return changes
