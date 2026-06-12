# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""Terraform → topology importer (``faultray import terraform``).

Converts ``terraform show -json`` output (state *or* plan) or a raw
``terraform.tfstate`` (version 4) into an editable FaultRay topology YAML
that feeds directly into ``faultray simulate -m <file>``.

Design contract (differs from :mod:`faultray.discovery.terraform` /
``tf-import``):

- Dependency edges are emitted **only when the input contains evidence**:
  explicit configuration references (plan JSON), ``depends_on``, attribute
  value cross-references (ARN / endpoint / id strings), or well-known AWS
  wiring patterns (ALB listener→target group→target, Lambda event source
  mappings, ECS task definitions).  No type-based cross joins.
- Dependency *type* inference is conservative: when the semantics are not
  explicit in the input, the edge is emitted as ``requires`` (full impact)
  so simulated availability errs toward the floor.
- Pass-through resources (target groups, listeners, task definitions,
  event source mappings) are collapsed into component→component edges
  instead of becoming phantom components.
- External HTTPS URLs found in Lambda / ECS task definition environment
  variables become ``external_api`` components, so third-party SaaS
  dependencies participate in availability math via their provider SLA.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

import yaml

from faultray.model.components import (
    SCHEMA_VERSION,
    Capacity,
    Component,
    ComponentType,
    Dependency,
    ExternalSLAConfig,
    RegionConfig,
)
from faultray.model.graph import InfraGraph

MAX_INPUT_BYTES = 10 * 1024 * 1024  # consistent with discovery.terraform

# --- Resource classification -------------------------------------------------

# AWS resources that become topology components.
RESOURCE_TYPE_MAP: dict[str, ComponentType] = {
    # Entry points / routing
    "aws_lb": ComponentType.LOAD_BALANCER,
    "aws_alb": ComponentType.LOAD_BALANCER,
    "aws_elb": ComponentType.LOAD_BALANCER,
    "aws_cloudfront_distribution": ComponentType.LOAD_BALANCER,
    "aws_api_gateway_rest_api": ComponentType.LOAD_BALANCER,
    "aws_apigatewayv2_api": ComponentType.LOAD_BALANCER,
    "aws_route53_record": ComponentType.DNS,
    # Compute
    "aws_instance": ComponentType.APP_SERVER,
    "aws_autoscaling_group": ComponentType.APP_SERVER,
    "aws_ecs_service": ComponentType.APP_SERVER,
    "aws_eks_cluster": ComponentType.APP_SERVER,
    "aws_lambda_function": ComponentType.SERVERLESS,
    # Data stores
    "aws_db_instance": ComponentType.DATABASE,
    "aws_rds_cluster": ComponentType.DATABASE,
    "aws_dynamodb_table": ComponentType.DATABASE,
    "aws_elasticache_cluster": ComponentType.CACHE,
    "aws_elasticache_replication_group": ComponentType.CACHE,
    # Messaging
    "aws_sqs_queue": ComponentType.QUEUE,
    "aws_sns_topic": ComponentType.QUEUE,
    "aws_mq_broker": ComponentType.QUEUE,
    # Storage
    "aws_s3_bucket": ComponentType.STORAGE,
    "aws_efs_file_system": ComponentType.STORAGE,
}

# Resources that never become components but carry wiring information.
PASS_THROUGH_TYPES: frozenset[str] = frozenset({
    "aws_lb_target_group",
    "aws_alb_target_group",
    "aws_lb_target_group_attachment",
    "aws_alb_target_group_attachment",
    "aws_lb_listener",
    "aws_alb_listener",
    "aws_lb_listener_rule",
    "aws_alb_listener_rule",
    "aws_ecs_task_definition",
    "aws_lambda_event_source_mapping",
    "aws_apigatewayv2_integration",
    "aws_apigatewayv2_route",
    "aws_api_gateway_integration",
    "aws_api_gateway_resource",
    "aws_api_gateway_method",
    "aws_rds_cluster_instance",
})

# Published AWS SLA commitments (monthly uptime %) for fully managed
# services.  These feed the external-SLA layer of the availability model —
# contractual floors, deliberately conservative vs observed availability.
MANAGED_SERVICE_SLA: dict[str, float] = {
    "aws_s3_bucket": 99.9,
    "aws_sqs_queue": 99.9,
    "aws_sns_topic": 99.9,
    "aws_route53_record": 100.0,
    "aws_dynamodb_table": 99.99,
    "aws_cloudfront_distribution": 99.9,
    "aws_lambda_function": 99.95,
    "aws_api_gateway_rest_api": 99.95,
    "aws_apigatewayv2_api": 99.95,
    "aws_efs_file_system": 99.9,
}

DEFAULT_EXTERNAL_API_SLA = 99.9

DEFAULT_CAPACITY: dict[ComponentType, Capacity] = {
    ComponentType.LOAD_BALANCER: Capacity(max_connections=50000, max_rps=100000),
    ComponentType.APP_SERVER: Capacity(
        max_connections=1000, connection_pool_size=200, timeout_seconds=30
    ),
    ComponentType.SERVERLESS: Capacity(max_connections=1000, timeout_seconds=30),
    ComponentType.DATABASE: Capacity(
        max_connections=200, max_disk_gb=500, timeout_seconds=60
    ),
    ComponentType.CACHE: Capacity(max_connections=10000, timeout_seconds=5),
    ComponentType.QUEUE: Capacity(max_connections=5000),
    ComponentType.STORAGE: Capacity(max_disk_gb=1000),
    ComponentType.DNS: Capacity(max_rps=100000),
    ComponentType.EXTERNAL_API: Capacity(max_connections=10000, timeout_seconds=10),
}

_PORT_DEFAULTS: dict[ComponentType, int] = {
    ComponentType.LOAD_BALANCER: 443,
    ComponentType.DATABASE: 5432,
    ComponentType.CACHE: 6379,
    ComponentType.QUEUE: 443,
    ComponentType.DNS: 53,
    ComponentType.EXTERNAL_API: 443,
}

# Attribute keys whose string values identify a resource to others.
_IDENTITY_KEYS: frozenset[str] = frozenset({
    "id",
    "arn",
    "endpoint",
    "reader_endpoint",
    "address",
    "primary_endpoint_address",
    "configuration_endpoint_address",
    "configuration_endpoint",
    "cache_nodes",
    "dns_name",
    "domain_name",
    "bucket_domain_name",
    "bucket_regional_domain_name",
    "url",
    "invoke_arn",
    "qualified_arn",
    "api_endpoint",
    "fqdn",
})

_MIN_IDENTITY_LEN = 8

# Hosts that are part of the imported infrastructure itself, not external
# SaaS dependencies.
_INTERNAL_HOST_RE = re.compile(
    r"(\.amazonaws\.com$|\.on\.aws$|\.internal$|\.local$|^localhost$|^\d+\.\d+\.\d+\.\d+$)"
)

_URL_RE = re.compile(r"https://[A-Za-z0-9._~:/?#\[\]@!$&'()*+,;=%-]+")

# AWS-style physical IDs (i-0abc…, sg-…, subnet-…) — valid identity probes
# even though they contain no ':' / '/' / '.' characters.
_AWS_ID_RE = re.compile(r"^[a-z]{1,12}-[0-9a-f]{8,17}$")


# --- Data carriers -----------------------------------------------------------


@dataclass
class RawResource:
    """A Terraform resource instance, format-normalised."""

    type: str
    name: str
    address: str
    values: dict
    depends_on: list[str] = field(default_factory=list)


@dataclass
class ImportedEdge:
    source: str
    target: str
    dep_type: str  # requires / optional / async
    evidence: str  # human-readable provenance for review


@dataclass
class TerraformImportResult:
    graph: InfraGraph
    edges: list[ImportedEdge]
    skipped_types: dict[str, int]
    warnings: list[str]
    source_format: str  # "plan" | "state" | "tfstate"

    @property
    def isolated_component_ids(self) -> list[str]:
        """Components with no edges at all — candidates for manual review."""
        connected = {e.source for e in self.edges} | {e.target for e in self.edges}
        return sorted(set(self.graph.components.keys()) - connected)


# --- Public API ---------------------------------------------------------------


def load_terraform_file(path: Path) -> TerraformImportResult:
    """Load and import a Terraform JSON file (state, plan, or raw tfstate)."""
    resolved = path.resolve()
    if not resolved.exists():
        raise ValueError(f"Input file does not exist: {resolved}")
    size = resolved.stat().st_size
    if size > MAX_INPUT_BYTES:
        raise ValueError(
            f"Input file too large ({size:,} bytes). Maximum: {MAX_INPUT_BYTES:,} bytes."
        )
    try:
        data = json.loads(resolved.read_text(encoding="utf-8", errors="replace"))
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Not valid JSON: {resolved}. Generate input with "
            f"'terraform show -json [planfile] > out.json'."
        ) from exc
    if not isinstance(data, dict):
        raise ValueError("Expected a JSON object at the top level.")
    return import_terraform(data)


def import_terraform(data: dict) -> TerraformImportResult:
    """Import parsed Terraform JSON into an InfraGraph with evidence-based edges."""
    source_format, resources, config_refs = _extract_resources(data)

    warnings: list[str] = []
    skipped: Counter[str] = Counter()
    components: dict[str, Component] = {}
    passthrough: dict[str, RawResource] = {}
    by_address: dict[str, RawResource] = {}

    for res in resources:
        by_address[res.address] = res
        if res.type in RESOURCE_TYPE_MAP:
            comp = _resource_to_component(res)
            components[res.address] = comp
        elif res.type in PASS_THROUGH_TYPES:
            passthrough[res.address] = res
        else:
            skipped[res.type] += 1

    _apply_rds_cluster_instances(components, passthrough, by_address)

    # Raw reference graph over ALL resources: A references B  =>  A -> B.
    raw_refs = _build_raw_references(by_address, config_refs)

    component_ids = set(components.keys())

    # Pattern edges first: their direction is semantically authoritative
    # (e.g. LB → backend), while raw references often point the other way
    # (an ECS service references its target group / listener).
    pattern_edges = (
        _edges_from_lb_wiring(raw_refs, components, passthrough)
        + _edges_from_event_source_mappings(raw_refs, components, passthrough)
        + _edges_from_api_gateway(raw_refs, components, passthrough)
    )
    suppressed_reverse = {(e.target, e.source) for e in pattern_edges}

    ref_edges = _edges_from_direct_refs(
        raw_refs, component_ids
    ) + _edges_from_passthrough_collapse(
        raw_refs, component_ids, set(passthrough.keys()), by_address
    )
    ref_edges = [
        e for e in ref_edges if (e.source, e.target) not in suppressed_reverse
    ]

    edges: list[ImportedEdge] = pattern_edges + ref_edges

    external_components, external_edges = _external_apis_from_env(
        components, passthrough, raw_refs, by_address
    )
    for comp in external_components:
        components[comp.id] = comp
    edges += external_edges

    graph = InfraGraph()
    for addr in sorted(components):
        graph.add_component(components[addr])

    final_edges = _add_edges_acyclic(graph, edges, warnings)

    return TerraformImportResult(
        graph=graph,
        edges=final_edges,
        skipped_types=dict(sorted(skipped.items())),
        warnings=warnings,
        source_format=source_format,
    )


def topology_yaml(result: TerraformImportResult) -> str:
    """Render the import result as topology YAML (loadable by model.loader)."""
    comp_entries = []
    for addr in sorted(result.graph.components):
        comp = result.graph.components[addr]
        entry: dict = {
            "id": comp.id,
            "name": comp.name,
            "type": comp.type.value,
        }
        if comp.host:
            entry["host"] = comp.host
        if comp.port:
            entry["port"] = comp.port
        if comp.replicas > 1:
            entry["replicas"] = comp.replicas
        cap = comp.capacity
        entry["capacity"] = {
            "max_connections": cap.max_connections,
            "timeout_seconds": cap.timeout_seconds,
        }
        if cap.max_disk_gb != Capacity().max_disk_gb:
            entry["capacity"]["max_disk_gb"] = cap.max_disk_gb
        if comp.external_sla is not None:
            entry["external_sla"] = {"provider_sla": comp.external_sla.provider_sla}
        if comp.region.region or comp.region.availability_zone:
            region: dict = {}
            if comp.region.region:
                region["region"] = comp.region.region
            if comp.region.availability_zone:
                region["availability_zone"] = comp.region.availability_zone
            entry["region"] = region
        if comp.parameters:
            entry["parameters"] = dict(comp.parameters)
        comp_entries.append(entry)

    dep_entries = [
        {
            "source": e.source,
            "target": e.target,
            "type": e.dep_type,
        }
        for e in sorted(result.edges, key=lambda e: (e.source, e.target))
    ]

    doc: dict = {"schema_version": SCHEMA_VERSION, "components": comp_entries}
    if dep_entries:
        doc["dependencies"] = dep_entries

    header_lines = [
        "# FaultRay topology — imported from Terraform "
        f"({result.source_format} JSON).",
        "# Review before relying on simulation results:",
        "#   - edges are evidence-based; semantics default to 'requires'",
        "#     (conservative). Relax to 'optional'/'async' where appropriate.",
        "#   - components with no edges need manual wiring.",
        "#",
        "# Edge evidence:",
    ]
    for e in sorted(result.edges, key=lambda e: (e.source, e.target)):
        header_lines.append(f"#   {e.source} -> {e.target}: {e.evidence}")
    if not result.edges:
        header_lines.append("#   (none found)")
    header = "\n".join(header_lines) + "\n"

    body = yaml.dump(
        doc, default_flow_style=False, sort_keys=False, allow_unicode=True, width=100
    )
    return header + body


# --- Input format handling ----------------------------------------------------


def _extract_resources(
    data: dict,
) -> tuple[str, list[RawResource], dict[str, set[str]]]:
    """Normalise the three supported input formats.

    Returns ``(source_format, resources, config_refs)`` where *config_refs*
    maps resource address → set of referenced addresses (plan JSON only).
    """
    resources: list[RawResource] = []
    config_refs: dict[str, set[str]] = {}

    if "planned_values" in data:
        source_format = "plan"
        _walk_values_module(data.get("planned_values", {}).get("root_module", {}), resources)
        _walk_config_module(data.get("configuration", {}).get("root_module", {}), "", config_refs)
    elif "values" in data:
        source_format = "state"
        _walk_values_module(data.get("values", {}).get("root_module", {}), resources)
        # `terraform show -json` for a state has no configuration section,
        # but may carry one when produced from a plan-less wrapper; use it
        # if present.
        if "configuration" in data:
            _walk_config_module(data["configuration"].get("root_module", {}), "", config_refs)
    elif "resources" in data:
        source_format = "tfstate"
        for block in data.get("resources", []):
            if block.get("mode") == "data":
                continue
            res_type = block.get("type", "")
            res_name = block.get("name", "")
            module_prefix = block.get("module", "")
            base = f"{module_prefix}." if module_prefix else ""
            instances = block.get("instances", [])
            for inst in instances:
                attrs = inst.get("attributes", {}) or {}
                index_key = inst.get("index_key")
                suffix = "" if index_key is None else f"[{json.dumps(index_key)}]" if isinstance(index_key, str) else f"[{index_key}]"
                resources.append(
                    RawResource(
                        type=res_type,
                        name=res_name,
                        address=f"{base}{res_type}.{res_name}{suffix}",
                        values=attrs,
                        depends_on=list(inst.get("dependencies", []) or []),
                    )
                )
    else:
        raise ValueError(
            "Unrecognised input. Expected 'terraform show -json' output "
            "(state or plan) or a terraform.tfstate (version 4) file."
        )

    return source_format, resources, config_refs


def _walk_values_module(module: dict, out: list[RawResource]) -> None:
    """Recursively collect resources from a (planned_)values module tree."""
    for res in module.get("resources", []) or []:
        if res.get("mode") == "data":
            continue
        out.append(
            RawResource(
                type=res.get("type", ""),
                name=res.get("name", ""),
                address=res.get("address", f"{res.get('type', '')}.{res.get('name', '')}"),
                values=res.get("values") or {},
                depends_on=list(res.get("depends_on", []) or []),
            )
        )
    for child in module.get("child_modules", []) or []:
        _walk_values_module(child, out)


def _walk_config_module(
    module: dict, address_prefix: str, out: dict[str, set[str]]
) -> None:
    """Recursively collect expression references from a configuration module."""
    for res in module.get("resources", []) or []:
        address = res.get("address", "")
        if address_prefix and not address.startswith(address_prefix):
            address = f"{address_prefix}{address}"
        refs: set[str] = set()
        _collect_references(res.get("expressions", {}), refs)
        for dep in res.get("depends_on", []) or []:
            refs.add(dep)
        if refs:
            prefixed = {f"{address_prefix}{r}" if address_prefix else r for r in refs}
            out.setdefault(address, set()).update(prefixed)
    for call_name, call in (module.get("module_calls", {}) or {}).items():
        child = call.get("module", {})
        _walk_config_module(child, f"{address_prefix}module.{call_name}.", out)


def _collect_references(node: object, out: set[str]) -> None:
    if isinstance(node, dict):
        for key, val in node.items():
            if key == "references" and isinstance(val, list):
                out.update(str(v) for v in val)
            else:
                _collect_references(val, out)
    elif isinstance(node, list):
        for item in node:
            _collect_references(item, out)


# --- Component construction ----------------------------------------------------


def _resource_to_component(res: RawResource) -> Component:
    comp_type = RESOURCE_TYPE_MAP[res.type]
    values = res.values

    tags = values.get("tags") if isinstance(values.get("tags"), dict) else {}
    name = (tags or {}).get("Name") or values.get("name") or values.get(
        "identifier"
    ) or values.get("bucket") or values.get("function_name") or res.name

    host = ""
    for key in (
        "endpoint",
        "address",
        "primary_endpoint_address",
        "configuration_endpoint_address",
        "dns_name",
        "domain_name",
        "bucket_regional_domain_name",
        "fqdn",
        "api_endpoint",
        "private_ip",
    ):
        val = values.get(key)
        if isinstance(val, str) and val:
            host = val.split(":")[0] if key in ("endpoint", "address") else val
            if host.startswith("https://"):
                host = urlparse(host).hostname or host
            break

    port = _extract_port(res.type, values, comp_type)
    replicas = _extract_replicas(res.type, values)
    capacity = _extract_capacity(values, comp_type)

    external_sla = None
    if res.type in MANAGED_SERVICE_SLA:
        external_sla = ExternalSLAConfig(provider_sla=MANAGED_SERVICE_SLA[res.type])

    region = RegionConfig()
    az = values.get("availability_zone")
    if isinstance(az, str) and az:
        region.availability_zone = az
        region.region = az[:-1] if az[-1].isalpha() else ""

    return Component(
        id=res.address,
        name=str(name),
        type=comp_type,
        host=host,
        port=port,
        replicas=replicas,
        capacity=capacity,
        external_sla=external_sla,
        region=region,
        parameters={
            "terraform_type": res.type,
            "terraform_address": res.address,
        },
    )


def _extract_port(res_type: str, values: dict, comp_type: ComponentType) -> int:
    port = values.get("port")
    if isinstance(port, (int, float)) and port:
        return int(port)
    if res_type in ("aws_db_instance", "aws_rds_cluster"):
        engine = str(values.get("engine", ""))
        if "mysql" in engine or "mariadb" in engine or "aurora-mysql" in engine:
            return 3306
        return 5432
    return _PORT_DEFAULTS.get(comp_type, 0)


def _extract_replicas(res_type: str, values: dict) -> int:
    for key in ("desired_count", "desired_capacity", "num_cache_nodes", "num_cache_clusters"):
        val = values.get(key)
        if isinstance(val, (int, float)) and val:
            return max(1, int(val))
    if values.get("multi_az"):
        return 2
    return 1


def _extract_capacity(values: dict, comp_type: ComponentType) -> Capacity:
    base = DEFAULT_CAPACITY.get(comp_type, Capacity()).model_copy(deep=True)
    storage = values.get("allocated_storage")
    if isinstance(storage, (int, float)) and storage:
        base.max_disk_gb = float(storage)
    instance_class = values.get("instance_class") or values.get("instance_type") or ""
    if isinstance(instance_class, str) and instance_class:
        base.max_connections = _estimate_connections(instance_class, comp_type)
    timeout = values.get("timeout")
    if isinstance(timeout, (int, float)) and timeout:
        base.timeout_seconds = float(timeout)
    return base


def _estimate_connections(instance_class: str, comp_type: ComponentType) -> int:
    size_map = {
        "micro": 50, "small": 100, "medium": 200,
        "large": 500, "xlarge": 1000, "2xlarge": 2000,
        "4xlarge": 5000, "8xlarge": 10000,
    }
    lowered = instance_class.lower()
    # Match the largest size token so "2xlarge" is not mistaken for "xlarge".
    for size in sorted(size_map, key=len, reverse=True):
        if size in lowered:
            conns = size_map[size]
            return conns if comp_type == ComponentType.DATABASE else conns * 2
    return 500


def _apply_rds_cluster_instances(
    components: dict[str, Component],
    passthrough: dict[str, RawResource],
    by_address: dict[str, RawResource],
) -> None:
    """Fold aws_rds_cluster_instance resources into their cluster's replica count."""
    counts: Counter[str] = Counter()
    for res in passthrough.values():
        if res.type != "aws_rds_cluster_instance":
            continue
        cluster_id = res.values.get("cluster_identifier", "")
        for addr, comp in components.items():
            raw = by_address.get(addr)
            if raw is None or raw.type != "aws_rds_cluster":
                continue
            if cluster_id and cluster_id in (
                raw.values.get("cluster_identifier", ""),
                raw.values.get("id", ""),
            ):
                counts[addr] += 1
    for addr, n in counts.items():
        components[addr].replicas = max(components[addr].replicas, n)


# --- Reference graph -----------------------------------------------------------


def _build_raw_references(
    by_address: dict[str, RawResource], config_refs: dict[str, set[str]]
) -> dict[str, dict[str, str]]:
    """Build A→{B: evidence} over all resources.

    Evidence sources, in decreasing precedence:
    1. plan configuration references
    2. depends_on / tfstate instance dependencies
    3. attribute identity matching (ARN / endpoint / id substrings)
    """
    known = set(by_address.keys())
    refs: dict[str, dict[str, str]] = {addr: {} for addr in known}

    def add(src: str, tgt: str, evidence: str) -> None:
        if src == tgt or src not in refs or tgt not in known:
            return
        refs[src].setdefault(tgt, evidence)

    for src, targets in config_refs.items():
        if src not in known:
            continue
        for ref in targets:
            tgt = _normalize_ref(ref, known)
            if tgt:
                add(src, tgt, "configuration reference")

    for addr, res in by_address.items():
        for dep in res.depends_on:
            tgt = _normalize_ref(dep, known)
            if tgt:
                add(addr, tgt, "depends_on")

    identity = _build_identity_index(by_address)
    # Deterministic match order: most specific (longest) identity first, so
    # the evidence string is stable across runs regardless of hash seeds.
    ordered_identity = sorted(identity.items(), key=lambda kv: (-len(kv[0]), kv[0]))
    for addr, res in by_address.items():
        strings = _collect_strings(res.values)
        for s in strings:
            for ident, owner in ordered_identity:
                if owner != addr and ident in s:
                    add(addr, owner, f"attribute reference ({ident[:60]})")

    return refs


def _normalize_ref(ref: str, known: set[str]) -> str | None:
    """Map a configuration reference to a known resource address.

    References may carry attribute/index suffixes
    (``aws_db_instance.main.endpoint``, ``aws_instance.web[0].id``); trim
    trailing segments until an address matches.
    """
    candidate = ref
    while candidate:
        if candidate in known:
            return candidate
        if "." not in candidate:
            return None
        candidate = candidate.rsplit(".", 1)[0]
    return None


def _build_identity_index(by_address: dict[str, RawResource]) -> dict[str, str]:
    """Map identifying attribute strings → owning resource address.

    Ambiguous values (owned by 2+ resources) are dropped.
    """
    owner: dict[str, str] = {}
    ambiguous: set[str] = set()
    for addr, res in by_address.items():
        for key in _IDENTITY_KEYS:
            val = res.values.get(key)
            for s in _iter_identity_strings(val):
                if len(s) < _MIN_IDENTITY_LEN:
                    continue
                if not any(ch in s for ch in (":", "/", ".")) and not _AWS_ID_RE.match(s):
                    continue  # too generic to be a safe substring probe
                if s in owner and owner[s] != addr:
                    ambiguous.add(s)
                else:
                    owner[s] = addr
    for s in ambiguous:
        owner.pop(s, None)
    return owner


def _iter_identity_strings(val: object):
    if isinstance(val, str) and val:
        yield val
    elif isinstance(val, list):
        for item in val:
            yield from _iter_identity_strings(item)
    elif isinstance(val, dict):
        for sub in val.values():
            yield from _iter_identity_strings(sub)


def _collect_strings(values: object, out: list[str] | None = None) -> list[str]:
    if out is None:
        out = []
    if isinstance(values, str):
        if values:
            out.append(values)
    elif isinstance(values, dict):
        for sub in values.values():
            _collect_strings(sub, out)
    elif isinstance(values, list):
        for item in values:
            _collect_strings(item, out)
    return out


# --- Edge derivation -----------------------------------------------------------


def _edges_from_direct_refs(
    raw_refs: dict[str, dict[str, str]], component_ids: set[str]
) -> list[ImportedEdge]:
    edges = []
    for src, targets in raw_refs.items():
        if src not in component_ids:
            continue
        for tgt, evidence in targets.items():
            if tgt in component_ids:
                edges.append(ImportedEdge(src, tgt, "requires", evidence))
    return edges


def _edges_from_passthrough_collapse(
    raw_refs: dict[str, dict[str, str]],
    component_ids: set[str],
    passthrough_ids: set[str],
    by_address: dict[str, RawResource],
) -> list[ImportedEdge]:
    """Walk component → passthrough… → component chains (e.g. ECS task defs)."""
    edges = []
    for src in sorted(component_ids):
        seen: set[str] = set()
        frontier = [
            (tgt, [tgt])
            for tgt in raw_refs.get(src, {})
            if tgt in passthrough_ids
        ]
        while frontier:
            node, path = frontier.pop()
            if node in seen:
                continue
            seen.add(node)
            for tgt in raw_refs.get(node, {}):
                if tgt == src:
                    continue
                if tgt in component_ids:
                    via = " -> ".join(
                        by_address[p].type if p in by_address else p for p in path
                    )
                    edges.append(
                        ImportedEdge(src, tgt, "requires", f"via {via}")
                    )
                elif tgt in passthrough_ids:
                    frontier.append((tgt, path + [tgt]))
    return edges


def _edges_from_lb_wiring(
    raw_refs: dict[str, dict[str, str]],
    components: dict[str, Component],
    passthrough: dict[str, RawResource],
) -> list[ImportedEdge]:
    """ALB/NLB wiring: listener + target group + attachments → LB → backend.

    Reference direction in Terraform points *at* the target group from both
    sides (listener references TG and LB; services/ASGs/attachments
    reference TG), so the dependency direction is fixed here semantically:
    the load balancer requires its backends.
    """
    tg_ids = {
        addr
        for addr, res in passthrough.items()
        if res.type in ("aws_lb_target_group", "aws_alb_target_group")
    }
    listener_ids = {
        addr
        for addr, res in passthrough.items()
        if res.type
        in (
            "aws_lb_listener",
            "aws_alb_listener",
            "aws_lb_listener_rule",
            "aws_alb_listener_rule",
        )
    }
    attachment_ids = {
        addr
        for addr, res in passthrough.items()
        if res.type
        in ("aws_lb_target_group_attachment", "aws_alb_target_group_attachment")
    }
    lb_ids = {
        addr
        for addr, comp in components.items()
        if comp.type == ComponentType.LOAD_BALANCER
    }

    tg_to_lbs: dict[str, set[str]] = {tg: set() for tg in tg_ids}
    tg_to_backends: dict[str, set[str]] = {tg: set() for tg in tg_ids}

    # Listener rules reference a listener, not the LB itself — resolve the
    # rule → listener → LB chain so path-routed target groups still wire up.
    listener_to_lbs: dict[str, set[str]] = {}
    for listener in listener_ids:
        listener_to_lbs[listener] = {
            t for t in raw_refs.get(listener, {}) if t in lb_ids
        }

    for listener in listener_ids:
        targets = raw_refs.get(listener, {})
        lbs = set(listener_to_lbs[listener])
        for t in targets:
            if t in listener_ids:
                lbs.update(listener_to_lbs[t])
        tgs = [t for t in targets if t in tg_ids]
        for tg in tgs:
            tg_to_lbs[tg].update(lbs)

    for attachment in attachment_ids:
        targets = raw_refs.get(attachment, {})
        tgs = [t for t in targets if t in tg_ids]
        backends = [t for t in targets if t in components]
        for tg in tgs:
            tg_to_backends[tg].update(backends)

    # ECS services / ASGs reference their target groups directly.
    for addr, comp in components.items():
        if comp.type not in (ComponentType.APP_SERVER, ComponentType.SERVERLESS):
            continue
        for tgt in raw_refs.get(addr, {}):
            if tgt in tg_ids:
                tg_to_backends[tgt].add(addr)

    edges = []
    for tg in sorted(tg_ids):
        for lb in sorted(tg_to_lbs[tg]):
            for backend in sorted(tg_to_backends[tg]):
                if lb != backend:
                    edges.append(
                        ImportedEdge(
                            lb,
                            backend,
                            "requires",
                            f"load balancer wiring via {passthrough[tg].address}",
                        )
                    )
    return edges


def _edges_from_event_source_mappings(
    raw_refs: dict[str, dict[str, str]],
    components: dict[str, Component],
    passthrough: dict[str, RawResource],
) -> list[ImportedEdge]:
    """Lambda event source mapping: the consumer function requires its source."""
    edges = []
    for addr, res in sorted(passthrough.items()):
        if res.type != "aws_lambda_event_source_mapping":
            continue
        targets = raw_refs.get(addr, {})
        functions = [
            t for t in targets if components.get(t) is not None
            and components[t].type == ComponentType.SERVERLESS
        ]
        sources = [
            t for t in targets if components.get(t) is not None
            and components[t].type in (ComponentType.QUEUE, ComponentType.DATABASE)
        ]
        for fn in functions:
            for src in sources:
                edges.append(
                    ImportedEdge(fn, src, "requires", "lambda event source mapping")
                )
    return edges


def _edges_from_api_gateway(
    raw_refs: dict[str, dict[str, str]],
    components: dict[str, Component],
    passthrough: dict[str, RawResource],
) -> list[ImportedEdge]:
    """API Gateway integrations: the API (router) requires its backend."""
    integration_types = (
        "aws_apigatewayv2_integration",
        "aws_apigatewayv2_route",
        "aws_api_gateway_integration",
        "aws_api_gateway_resource",
        "aws_api_gateway_method",
    )
    api_types = ("aws_api_gateway_rest_api", "aws_apigatewayv2_api")
    edges = []
    for addr, res in sorted(passthrough.items()):
        if res.type not in integration_types:
            continue
        targets = raw_refs.get(addr, {})
        apis = [
            t
            for t in targets
            if t in components
            and components[t].parameters.get("terraform_type") in api_types
        ]
        backends = [
            t
            for t in targets
            if t in components
            and components[t].parameters.get("terraform_type") not in api_types
        ]
        for api in apis:
            for backend in backends:
                edges.append(
                    ImportedEdge(api, backend, "requires", "api gateway integration")
                )
    return edges


def _external_apis_from_env(
    components: dict[str, Component],
    passthrough: dict[str, RawResource],
    raw_refs: dict[str, dict[str, str]],
    by_address: dict[str, RawResource],
) -> tuple[list[Component], list[ImportedEdge]]:
    """Synthesise external_api components from HTTPS URLs in env variables.

    Sources scanned: Lambda ``environment.variables`` and ECS task
    definition ``container_definitions`` (attributed to the services that
    use the task definition).
    """
    found: dict[str, set[str]] = {}  # host -> consumer component addresses

    def scan(consumer: str, blob: object) -> None:
        for s in _collect_strings(blob):
            for url in _URL_RE.findall(s):
                host = urlparse(url).hostname
                if not host or _INTERNAL_HOST_RE.search(host):
                    continue
                found.setdefault(host, set()).add(consumer)

    for addr, comp in components.items():
        if comp.type == ComponentType.SERVERLESS and addr in by_address:
            scan(addr, by_address[addr].values.get("environment"))

    # Task definitions: attribute their env URLs to consuming ECS services.
    taskdef_consumers: dict[str, set[str]] = {}
    for addr, comp in components.items():
        for tgt in raw_refs.get(addr, {}):
            res = passthrough.get(tgt)
            if res is not None and res.type == "aws_ecs_task_definition":
                taskdef_consumers.setdefault(tgt, set()).add(addr)
    for taskdef_addr, consumers in taskdef_consumers.items():
        blob = passthrough[taskdef_addr].values.get("container_definitions")
        for consumer in consumers:
            scan(consumer, blob)

    new_components: list[Component] = []
    edges: list[ImportedEdge] = []
    for host in sorted(found):
        ext_id = f"external:{host}"
        new_components.append(
            Component(
                id=ext_id,
                name=host,
                type=ComponentType.EXTERNAL_API,
                host=host,
                port=443,
                capacity=DEFAULT_CAPACITY[ComponentType.EXTERNAL_API].model_copy(
                    deep=True
                ),
                external_sla=ExternalSLAConfig(provider_sla=DEFAULT_EXTERNAL_API_SLA),
                parameters={"source": "environment variable URL"},
            )
        )
        for consumer in sorted(found[host]):
            edges.append(
                ImportedEdge(
                    consumer, ext_id, "requires", "https URL in environment variables"
                )
            )
    return new_components, edges


# --- Graph assembly -------------------------------------------------------------


def _add_edges_acyclic(
    graph: InfraGraph, edges: list[ImportedEdge], warnings: list[str]
) -> list[ImportedEdge]:
    """Dedupe edges and add them to the graph, skipping any that close a cycle.

    The model loader rejects cyclic topologies, so a conservative import
    must never emit one.  Edges are processed in deterministic order; an
    edge whose reverse path already exists is dropped with a warning.
    """
    import networkx as nx

    deduped: dict[tuple[str, str], ImportedEdge] = {}
    for edge in edges:
        if edge.source == edge.target:
            continue
        deduped.setdefault((edge.source, edge.target), edge)

    # Insertion order is priority order (pattern edges were appended first),
    # so on a cycle conflict the higher-confidence edge wins deterministically.
    final: list[ImportedEdge] = []
    for (src, tgt), edge in deduped.items():
        if graph.get_component(src) is None or graph.get_component(tgt) is None:
            continue
        if nx.has_path(graph._graph, tgt, src):
            warnings.append(
                f"Skipped edge {src} -> {tgt} ({edge.evidence}): would create "
                f"a dependency cycle. Review and add manually if the reverse "
                f"path is wrong."
            )
            continue
        graph.add_dependency(
            Dependency(
                source_id=src,
                target_id=tgt,
                dependency_type=edge.dep_type,
                weight=1.0,
            )
        )
        final.append(edge)
    return final
