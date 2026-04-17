# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""As-is IaC exporter for FaultRay.

Converts the current FaultRay infrastructure model (InfraGraph) into
Infrastructure-as-Code files that represent the infrastructure exactly as it
was discovered — not a remediation plan, but a snapshot export.

Supported output formats:
- Terraform HCL (AWS provider)
- CloudFormation YAML (AWS)
- Kubernetes manifests (YAML)

SPOF annotations (--mark-spof) embed FaultRay analysis comments directly in
the generated code so engineers can see resilience issues inline.
"""

from __future__ import annotations

import re
import textwrap
from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import Any

from faultray.model.components import Component, ComponentType
from faultray.model.graph import InfraGraph


# ---------------------------------------------------------------------------
# Public enums / data classes
# ---------------------------------------------------------------------------


class ExportFormat(str, Enum):
    """Supported as-is export formats."""

    TERRAFORM = "terraform"
    CLOUDFORMATION = "cloudformation"
    KUBERNETES = "kubernetes"


@dataclass
class IacExportResult:
    """Result of an as-is IaC export operation."""

    format: ExportFormat
    files: dict[str, str] = field(default_factory=dict)  # filename -> content
    warnings: list[str] = field(default_factory=list)
    spof_components: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _tf_id(name: str) -> str:
    """Sanitise a component id/name into a valid Terraform resource label."""
    return re.sub(r"[^a-zA-Z0-9]", "_", name).strip("_").lower()


def _cfn_id(name: str) -> str:
    """Sanitise a name into a valid CloudFormation logical ID (PascalCase-safe)."""
    cleaned = re.sub(r"[^a-zA-Z0-9]", " ", name).title().replace(" ", "")
    return cleaned or "Resource"


def _k8s_name(name: str) -> str:
    """Sanitise a name into a valid Kubernetes resource name (lowercase, dashes)."""
    return re.sub(r"[^a-z0-9-]", "-", name.lower()).strip("-")


def _today() -> str:
    return date.today().isoformat()


_DEFAULT_INSTANCE_TYPE: dict[ComponentType, str] = {
    ComponentType.LOAD_BALANCER: "t3.small",
    ComponentType.WEB_SERVER: "t3.small",
    ComponentType.APP_SERVER: "t3.medium",
    ComponentType.DATABASE: "db.t3.medium",
    ComponentType.CACHE: "cache.t3.medium",
    ComponentType.QUEUE: "mq.m5.large",
    ComponentType.STORAGE: "n/a",
    ComponentType.DNS: "n/a",
    ComponentType.EXTERNAL_API: "n/a",
    ComponentType.CUSTOM: "t3.medium",
    ComponentType.AI_AGENT: "t3.medium",
    ComponentType.LLM_ENDPOINT: "t3.xlarge",
    ComponentType.TOOL_SERVICE: "t3.medium",
    ComponentType.AGENT_ORCHESTRATOR: "t3.large",
}

_DEFAULT_PORT: dict[ComponentType, int] = {
    ComponentType.LOAD_BALANCER: 80,
    ComponentType.WEB_SERVER: 80,
    ComponentType.APP_SERVER: 8080,
    ComponentType.DATABASE: 5432,
    ComponentType.CACHE: 6379,
    ComponentType.QUEUE: 5672,
    ComponentType.STORAGE: 9000,
    ComponentType.DNS: 53,
    ComponentType.EXTERNAL_API: 443,
    ComponentType.CUSTOM: 8080,
    ComponentType.AI_AGENT: 8080,
    ComponentType.LLM_ENDPOINT: 443,
    ComponentType.TOOL_SERVICE: 8080,
    ComponentType.AGENT_ORCHESTRATOR: 8080,
}

_DEFAULT_K8S_IMAGE: dict[ComponentType, str] = {
    ComponentType.LOAD_BALANCER: "nginx:1.25-alpine",
    ComponentType.WEB_SERVER: "nginx:1.25-alpine",
    ComponentType.APP_SERVER: "node:20-alpine",
    ComponentType.DATABASE: "postgres:16-alpine",
    ComponentType.CACHE: "redis:7-alpine",
    ComponentType.QUEUE: "rabbitmq:3-management-alpine",
    ComponentType.STORAGE: "minio/minio:latest",
    ComponentType.DNS: "coredns/coredns:1.11",
    ComponentType.EXTERNAL_API: "alpine:3.19",
    ComponentType.CUSTOM: "alpine:3.19",
    ComponentType.AI_AGENT: "python:3.12-slim",
    ComponentType.LLM_ENDPOINT: "python:3.12-slim",
    ComponentType.TOOL_SERVICE: "python:3.12-slim",
    ComponentType.AGENT_ORCHESTRATOR: "python:3.12-slim",
}


def _comp_port(comp: Component) -> int:
    return comp.port if comp.port > 0 else _DEFAULT_PORT.get(comp.type, 8080)


# ---------------------------------------------------------------------------
# SPOF detection helpers
# ---------------------------------------------------------------------------


def _is_spof(comp: Component, graph: InfraGraph) -> bool:
    """Return True if the component is a potential Single Point of Failure."""
    dependents = graph.get_dependents(comp.id)
    return comp.replicas <= 1 and len(dependents) > 0 and not comp.failover.enabled


def _spof_comment_tf(comp: Component, graph: InfraGraph) -> str:
    """Return a Terraform SPOF warning comment block, or empty string."""
    if not _is_spof(comp, graph):
        return ""
    dependents = graph.get_dependents(comp.id)
    dep_names = ", ".join(d.name for d in dependents[:5])
    return textwrap.dedent(f"""\
        # ⚠️  FAULTRAY WARNING: Single Point of Failure detected
        # Component '{comp.name}' has {len(dependents)} dependent(s): {dep_names}
        # replicas={comp.replicas}, failover.enabled={comp.failover.enabled}
        # Recommendation: increase replicas or enable failover
    """)


def _spof_comment_cfn(comp: Component, graph: InfraGraph) -> str:
    """Return a CloudFormation SPOF warning comment block, or empty string."""
    if not _is_spof(comp, graph):
        return ""
    dependents = graph.get_dependents(comp.id)
    dep_names = ", ".join(d.name for d in dependents[:5])
    return (
        f"  # ⚠️  FAULTRAY WARNING: SPOF — '{comp.name}' has "
        f"{len(dependents)} dependent(s): {dep_names}\n"
        f"  # Recommendation: increase replicas or enable failover\n"
    )


def _spof_comment_k8s(comp: Component, graph: InfraGraph) -> str:
    """Return a Kubernetes SPOF warning comment, or empty string."""
    if not _is_spof(comp, graph):
        return ""
    dependents = graph.get_dependents(comp.id)
    dep_names = ", ".join(d.name for d in dependents[:5])
    return (
        f"  # ⚠️  FAULTRAY WARNING: SPOF — '{comp.name}' has "
        f"{len(dependents)} dependent(s): {dep_names}\n"
        f"  # Recommendation: set replicas > 1 or configure PodDisruptionBudget\n"
    )


# ---------------------------------------------------------------------------
# Terraform HCL generation
# ---------------------------------------------------------------------------


def _tf_header(region: str, version: str) -> str:
    today = _today()
    return textwrap.dedent(f"""\
        # Generated by FaultRay v{version}
        # Source: faultray iac-export --provider aws
        # Generated: {today}
        # NOTE: Placeholder values (ami-xxx, var.*) must be filled before apply.

        terraform {{
          required_version = ">= 1.5"
          required_providers {{
            aws = {{
              source  = "hashicorp/aws"
              version = "~> 5.0"
            }}
          }}
        }}

        provider "aws" {{
          region = "{region}"
        }}

        variable "vpc_id" {{
          description = "VPC ID for resource deployment"
          type        = string
        }}

        variable "subnet_ids" {{
          description = "Subnet IDs for multi-AZ deployment"
          type        = list(string)
        }}

    """)


def _tf_load_balancer(comp: Component, sid: str, graph: InfraGraph, mark_spof: bool, include_comments: bool) -> str:  # noqa: FBT001
    port = _comp_port(comp)
    today = _today()
    parts: list[str] = []
    if mark_spof:
        parts.append(_spof_comment_tf(comp, graph))
    parts.append(f'resource "aws_lb" "{sid}" {{\n')
    if include_comments:
        parts.append(f'  # {comp.name} — discovered by FaultRay on {today}\n')
    parts.append(f'  name               = "{comp.name}"\n')
    parts.append('  internal           = false\n')
    parts.append('  load_balancer_type = "application"\n')
    parts.append(f'  security_groups    = [aws_security_group.{sid}_sg.id]\n')
    parts.append('  subnets            = var.subnet_ids\n')
    parts.append('\n')
    parts.append('  tags = {\n')
    parts.append(f'    Name         = "{comp.name}"\n')
    parts.append('    ManagedBy    = "faultray"\n')
    parts.append(f'    DiscoveredAt = "{today}"\n')
    parts.append('  }\n')
    parts.append('}\n')
    parts.append('\n')
    parts.append(f'resource "aws_lb_target_group" "{sid}_tg" {{\n')
    parts.append(f'  name     = "{comp.name}-tg"\n')
    parts.append(f'  port     = {port}\n')
    parts.append('  protocol = "HTTP"\n')
    parts.append('  vpc_id   = var.vpc_id\n')
    parts.append('\n')
    parts.append('  tags = {\n')
    parts.append(f'    Name      = "{comp.name}-tg"\n')
    parts.append('    ManagedBy = "faultray"\n')
    parts.append('  }\n')
    parts.append('}\n')
    parts.append('\n')
    parts.append(f'resource "aws_lb_listener" "{sid}_listener" {{\n')
    parts.append(f'  load_balancer_arn = aws_lb.{sid}.arn\n')
    parts.append(f'  port              = {port}\n')
    parts.append('  protocol          = "HTTP"\n')
    parts.append('\n')
    parts.append('  default_action {\n')
    parts.append('    type             = "forward"\n')
    parts.append(f'    target_group_arn = aws_lb_target_group.{sid}_tg.arn\n')
    parts.append('  }\n')
    parts.append('}\n')
    parts.append('\n')
    parts.append(f'resource "aws_security_group" "{sid}_sg" {{\n')
    parts.append(f'  name        = "{comp.name}-sg"\n')
    parts.append(f'  description = "Security group for {comp.name}"\n')
    parts.append('  vpc_id      = var.vpc_id\n')
    parts.append('\n')
    parts.append('  ingress {\n')
    parts.append(f'    from_port   = {port}\n')
    parts.append(f'    to_port     = {port}\n')
    parts.append('    protocol    = "tcp"\n')
    parts.append('    cidr_blocks = ["0.0.0.0/0"]\n')
    parts.append('  }\n')
    parts.append('\n')
    parts.append('  egress {\n')
    parts.append('    from_port   = 0\n')
    parts.append('    to_port     = 0\n')
    parts.append('    protocol    = "-1"\n')
    parts.append('    cidr_blocks = ["0.0.0.0/0"]\n')
    parts.append('  }\n')
    parts.append('\n')
    parts.append('  tags = {\n')
    parts.append(f'    Name      = "{comp.name}-sg"\n')
    parts.append('    ManagedBy = "faultray"\n')
    parts.append('  }\n')
    parts.append('}\n')
    parts.append('\n')
    return "".join(parts)


def _tf_app_server(comp: Component, sid: str, graph: InfraGraph, mark_spof: bool, include_comments: bool) -> str:  # noqa: FBT001
    itype = _DEFAULT_INSTANCE_TYPE.get(comp.type, "t3.medium")
    today = _today()
    parts: list[str] = []
    if mark_spof:
        parts.append(_spof_comment_tf(comp, graph))
    parts.append(f'resource "aws_instance" "{sid}" {{\n')
    if include_comments:
        parts.append(f'  # {comp.name} — discovered by FaultRay on {today}\n')
    if comp.replicas > 1:
        parts.append(f'  count         = {comp.replicas}\n')
    parts.append('  ami           = "ami-xxx"  # Placeholder — replace with actual AMI\n')
    parts.append(f'  instance_type = "{itype}"\n')
    parts.append('\n')
    parts.append('  tags = {\n')
    parts.append(f'    Name         = "{comp.name}"\n')
    parts.append('    ManagedBy    = "faultray"\n')
    parts.append(f'    DiscoveredAt = "{today}"\n')
    parts.append('  }\n')
    parts.append('}\n')
    parts.append('\n')
    return "".join(parts)


def _tf_database(comp: Component, sid: str, graph: InfraGraph, mark_spof: bool, include_comments: bool) -> str:  # noqa: FBT001
    itype = _DEFAULT_INSTANCE_TYPE.get(comp.type, "db.t3.medium")
    today = _today()
    multi_az = str(comp.replicas > 1 or comp.failover.enabled).lower()
    spof = _is_spof(comp, graph)
    parts: list[str] = []
    if mark_spof:
        parts.append(_spof_comment_tf(comp, graph))
    parts.append(f'resource "aws_db_instance" "{sid}" {{\n')
    if include_comments:
        parts.append(f'  # {comp.name} — discovered by FaultRay on {today}\n')
    parts.append('  engine         = "postgres"  # Placeholder\n')
    parts.append(f'  instance_class = "{itype}"\n')
    if mark_spof and spof:
        parts.append('  # WARNING: SPOF detected by FaultRay — enable multi_az = true\n')
    parts.append(f'  multi_az       = {multi_az}\n')
    parts.append('  username       = "admin"        # Placeholder\n')
    parts.append('  password       = "CHANGE_ME"    # Placeholder — use aws_secretsmanager_secret\n')
    parts.append('  skip_final_snapshot = true\n')
    parts.append('\n')
    parts.append('  tags = {\n')
    parts.append(f'    Name         = "{comp.name}"\n')
    parts.append('    ManagedBy    = "faultray"\n')
    parts.append(f'    DiscoveredAt = "{today}"\n')
    parts.append('  }\n')
    parts.append('}\n')
    parts.append('\n')
    return "".join(parts)


def _tf_cache(comp: Component, sid: str, graph: InfraGraph, mark_spof: bool, include_comments: bool) -> str:  # noqa: FBT001
    itype = _DEFAULT_INSTANCE_TYPE.get(comp.type, "cache.t3.medium")
    today = _today()
    num_clusters = max(comp.replicas, 1)
    auto_failover = str(num_clusters > 1).lower()
    spof = _is_spof(comp, graph)
    parts: list[str] = []
    if mark_spof:
        parts.append(_spof_comment_tf(comp, graph))
    parts.append(f'resource "aws_elasticache_replication_group" "{sid}" {{\n')
    if include_comments:
        parts.append(f'  # {comp.name} — discovered by FaultRay on {today}\n')
    parts.append(f'  replication_group_id       = "{comp.name}"\n')
    parts.append(f'  description                = "{comp.name} cache cluster"\n')
    parts.append(f'  node_type                  = "{itype}"\n')
    if mark_spof and spof:
        parts.append('  # WARNING: SPOF — set num_cache_clusters >= 2 and automatic_failover_enabled = true\n')
    parts.append(f'  num_cache_clusters         = {num_clusters}\n')
    parts.append(f'  automatic_failover_enabled = {auto_failover}\n')
    parts.append('\n')
    parts.append('  tags = {\n')
    parts.append(f'    Name         = "{comp.name}"\n')
    parts.append('    ManagedBy    = "faultray"\n')
    parts.append(f'    DiscoveredAt = "{today}"\n')
    parts.append('  }\n')
    parts.append('}\n')
    parts.append('\n')
    return "".join(parts)


def _tf_queue(comp: Component, sid: str, graph: InfraGraph, mark_spof: bool, include_comments: bool) -> str:  # noqa: FBT001
    today = _today()
    parts: list[str] = []
    if mark_spof:
        parts.append(_spof_comment_tf(comp, graph))
    parts.append(f'resource "aws_sqs_queue" "{sid}" {{\n')
    if include_comments:
        parts.append(f'  # {comp.name} — discovered by FaultRay on {today}\n')
    parts.append(f'  name = "{comp.name}"\n')
    parts.append('\n')
    parts.append('  tags = {\n')
    parts.append(f'    Name         = "{comp.name}"\n')
    parts.append('    ManagedBy    = "faultray"\n')
    parts.append(f'    DiscoveredAt = "{today}"\n')
    parts.append('  }\n')
    parts.append('}\n')
    parts.append('\n')
    return "".join(parts)


def _tf_storage(comp: Component, sid: str, graph: InfraGraph, mark_spof: bool, include_comments: bool) -> str:  # noqa: FBT001
    today = _today()
    parts: list[str] = []
    if mark_spof:
        parts.append(_spof_comment_tf(comp, graph))
    parts.append(f'resource "aws_s3_bucket" "{sid}" {{\n')
    if include_comments:
        parts.append(f'  # {comp.name} — discovered by FaultRay on {today}\n')
    parts.append(f'  bucket = "{comp.name}"\n')
    parts.append('\n')
    parts.append('  tags = {\n')
    parts.append(f'    Name         = "{comp.name}"\n')
    parts.append('    ManagedBy    = "faultray"\n')
    parts.append(f'    DiscoveredAt = "{today}"\n')
    parts.append('  }\n')
    parts.append('}\n')
    parts.append('\n')
    return "".join(parts)


def _tf_dns(comp: Component, sid: str, graph: InfraGraph, mark_spof: bool, include_comments: bool) -> str:  # noqa: FBT001
    today = _today()
    parts: list[str] = []
    if mark_spof:
        parts.append(_spof_comment_tf(comp, graph))
    parts.append(f'resource "aws_route53_record" "{sid}" {{\n')
    if include_comments:
        parts.append(f'  # {comp.name} — discovered by FaultRay on {today}\n')
    parts.append('  zone_id = "PLACEHOLDER"  # Replace with aws_route53_zone.<name>.zone_id\n')
    parts.append(f'  name    = "{comp.name}"\n')
    parts.append('  type    = "A"\n')
    parts.append('  ttl     = 300\n')
    parts.append('  records = ["0.0.0.0"]  # Placeholder — replace with actual IP/alias\n')
    parts.append('  # ManagedBy    = faultray\n')
    parts.append(f'  # DiscoveredAt = {today}\n')
    parts.append('}\n')
    parts.append('\n')
    return "".join(parts)


def _tf_custom(comp: Component, sid: str, graph: InfraGraph, mark_spof: bool, include_comments: bool) -> str:  # noqa: FBT001
    """Fallback: emit an aws_instance for unknown/custom/AI component types."""
    return _tf_app_server(comp, sid, graph, mark_spof, include_comments)


_TF_DISPATCH: dict[ComponentType, Any] = {
    ComponentType.LOAD_BALANCER: _tf_load_balancer,
    ComponentType.WEB_SERVER: _tf_app_server,
    ComponentType.APP_SERVER: _tf_app_server,
    ComponentType.DATABASE: _tf_database,
    ComponentType.CACHE: _tf_cache,
    ComponentType.QUEUE: _tf_queue,
    ComponentType.STORAGE: _tf_storage,
    ComponentType.DNS: _tf_dns,
    ComponentType.EXTERNAL_API: None,  # skip — not a managed AWS resource
    ComponentType.CUSTOM: _tf_custom,
    ComponentType.AI_AGENT: _tf_custom,
    ComponentType.LLM_ENDPOINT: _tf_custom,
    ComponentType.TOOL_SERVICE: _tf_custom,
    ComponentType.AGENT_ORCHESTRATOR: _tf_custom,
}


def _generate_terraform(
    graph: InfraGraph,
    region: str,
    include_comments: bool,
    mark_spof: bool,
    version: str,
) -> IacExportResult:
    result = IacExportResult(format=ExportFormat.TERRAFORM)
    blocks: list[str] = [_tf_header(region, version)]
    spofs: list[str] = []

    for comp in graph.components.values():
        sid = _tf_id(comp.id)
        fn = _TF_DISPATCH.get(comp.type)
        if fn is None:
            result.warnings.append(
                f"Skipped '{comp.name}' ({comp.type.value}): not a managed AWS Terraform resource."
            )
            continue
        blocks.append(fn(comp, sid, graph, mark_spof, include_comments))
        if mark_spof and _is_spof(comp, graph):
            spofs.append(comp.name)

    result.files["main.tf"] = "".join(blocks)
    result.spof_components = spofs
    return result


# ---------------------------------------------------------------------------
# CloudFormation YAML generation
# ---------------------------------------------------------------------------


def _cfn_header(version: str) -> str:
    today = _today()
    return textwrap.dedent(f"""\
        # Generated by FaultRay v{version}
        # Source: faultray iac-export --provider aws --format cloudformation
        # Generated: {today}
        # NOTE: Placeholder values must be filled before deploying.
        AWSTemplateFormatVersion: "2010-09-09"
        Description: "FaultRay as-is infrastructure export — {today}"

        Parameters:
          VpcId:
            Type: AWS::EC2::VPC::Id
            Description: VPC for resource deployment
          SubnetIds:
            Type: List<AWS::EC2::Subnet::Id>
            Description: Subnets for multi-AZ deployment

        Resources:
    """)


def _cfn_load_balancer(comp: Component, cid: str, graph: InfraGraph, mark_spof: bool) -> str:
    today = _today()
    port = _comp_port(comp)
    parts: list[str] = []
    if mark_spof:
        parts.append(_spof_comment_cfn(comp, graph))
    parts.append(f'  {cid}ALB:\n')
    parts.append('    Type: AWS::ElasticLoadBalancingV2::LoadBalancer\n')
    parts.append('    Properties:\n')
    parts.append(f'      Name: "{comp.name}"\n')
    parts.append('      Scheme: internet-facing\n')
    parts.append('      Type: application\n')
    parts.append('      Subnets: !Ref SubnetIds\n')
    parts.append('      Tags:\n')
    parts.append('        - Key: Name\n')
    parts.append(f'          Value: "{comp.name}"\n')
    parts.append('        - Key: ManagedBy\n')
    parts.append('          Value: faultray\n')
    parts.append('        - Key: DiscoveredAt\n')
    parts.append(f'          Value: "{today}"\n')
    parts.append('\n')
    parts.append(f'  {cid}TargetGroup:\n')
    parts.append('    Type: AWS::ElasticLoadBalancingV2::TargetGroup\n')
    parts.append('    Properties:\n')
    parts.append(f'      Name: "{comp.name}-tg"\n')
    parts.append(f'      Port: {port}\n')
    parts.append('      Protocol: HTTP\n')
    parts.append('      VpcId: !Ref VpcId\n')
    parts.append('      Tags:\n')
    parts.append('        - Key: Name\n')
    parts.append(f'          Value: "{comp.name}-tg"\n')
    parts.append('        - Key: ManagedBy\n')
    parts.append('          Value: faultray\n')
    parts.append('\n')
    return "".join(parts)


def _cfn_instance(comp: Component, cid: str, graph: InfraGraph, mark_spof: bool) -> str:
    itype = _DEFAULT_INSTANCE_TYPE.get(comp.type, "t3.medium")
    today = _today()
    parts: list[str] = []
    if mark_spof:
        parts.append(_spof_comment_cfn(comp, graph))
    parts.append(f'  {cid}:\n')
    parts.append('    Type: AWS::EC2::Instance\n')
    parts.append('    Properties:\n')
    parts.append('      ImageId: ami-xxx  # Placeholder\n')
    parts.append(f'      InstanceType: {itype}\n')
    parts.append('      Tags:\n')
    parts.append('        - Key: Name\n')
    parts.append(f'          Value: "{comp.name}"\n')
    parts.append('        - Key: ManagedBy\n')
    parts.append('          Value: faultray\n')
    parts.append('        - Key: DiscoveredAt\n')
    parts.append(f'          Value: "{today}"\n')
    parts.append('\n')
    return "".join(parts)


def _cfn_database(comp: Component, cid: str, graph: InfraGraph, mark_spof: bool) -> str:
    itype = _DEFAULT_INSTANCE_TYPE.get(comp.type, "db.t3.medium")
    today = _today()
    multi_az = str(comp.replicas > 1 or comp.failover.enabled)
    spof = _is_spof(comp, graph)
    parts: list[str] = []
    if mark_spof:
        parts.append(_spof_comment_cfn(comp, graph))
    parts.append(f'  {cid}:\n')
    parts.append('    Type: AWS::RDS::DBInstance\n')
    parts.append('    Properties:\n')
    parts.append(f'      DBInstanceIdentifier: "{comp.name}"\n')
    parts.append(f'      DBInstanceClass: {itype}\n')
    parts.append('      Engine: postgres\n')
    if mark_spof and spof:
        parts.append('      # ⚠️  FAULTRAY: Set MultiAZ: true to eliminate SPOF\n')
    parts.append(f'      MultiAZ: {multi_az}\n')
    parts.append('      MasterUsername: admin  # Placeholder\n')
    parts.append('      MasterUserPassword: CHANGE_ME  # Placeholder\n')
    parts.append('      StorageType: gp3\n')
    parts.append('      AllocatedStorage: "20"\n')
    parts.append('      Tags:\n')
    parts.append('        - Key: Name\n')
    parts.append(f'          Value: "{comp.name}"\n')
    parts.append('        - Key: ManagedBy\n')
    parts.append('          Value: faultray\n')
    parts.append('        - Key: DiscoveredAt\n')
    parts.append(f'          Value: "{today}"\n')
    parts.append('\n')
    return "".join(parts)


def _cfn_queue(comp: Component, cid: str, graph: InfraGraph, mark_spof: bool) -> str:
    today = _today()
    parts: list[str] = []
    if mark_spof:
        parts.append(_spof_comment_cfn(comp, graph))
    parts.append(f'  {cid}:\n')
    parts.append('    Type: AWS::SQS::Queue\n')
    parts.append('    Properties:\n')
    parts.append(f'      QueueName: "{comp.name}"\n')
    parts.append('      Tags:\n')
    parts.append('        - Key: Name\n')
    parts.append(f'          Value: "{comp.name}"\n')
    parts.append('        - Key: ManagedBy\n')
    parts.append('          Value: faultray\n')
    parts.append('        - Key: DiscoveredAt\n')
    parts.append(f'          Value: "{today}"\n')
    parts.append('\n')
    return "".join(parts)


def _cfn_storage(comp: Component, cid: str, graph: InfraGraph, mark_spof: bool) -> str:
    today = _today()
    parts: list[str] = []
    if mark_spof:
        parts.append(_spof_comment_cfn(comp, graph))
    parts.append(f'  {cid}:\n')
    parts.append('    Type: AWS::S3::Bucket\n')
    parts.append('    Properties:\n')
    parts.append(f'      BucketName: "{comp.name}"\n')
    parts.append('      Tags:\n')
    parts.append('        - Key: Name\n')
    parts.append(f'          Value: "{comp.name}"\n')
    parts.append('        - Key: ManagedBy\n')
    parts.append('          Value: faultray\n')
    parts.append('        - Key: DiscoveredAt\n')
    parts.append(f'          Value: "{today}"\n')
    parts.append('\n')
    return "".join(parts)


_CFN_DISPATCH: dict[ComponentType, Any] = {
    ComponentType.LOAD_BALANCER: _cfn_load_balancer,
    ComponentType.WEB_SERVER: _cfn_instance,
    ComponentType.APP_SERVER: _cfn_instance,
    ComponentType.DATABASE: _cfn_database,
    ComponentType.CACHE: None,  # ElastiCache CFN is verbose — skip with warning
    ComponentType.QUEUE: _cfn_queue,
    ComponentType.STORAGE: _cfn_storage,
    ComponentType.DNS: None,
    ComponentType.EXTERNAL_API: None,
    ComponentType.CUSTOM: _cfn_instance,
    ComponentType.AI_AGENT: _cfn_instance,
    ComponentType.LLM_ENDPOINT: _cfn_instance,
    ComponentType.TOOL_SERVICE: _cfn_instance,
    ComponentType.AGENT_ORCHESTRATOR: _cfn_instance,
}


def _generate_cloudformation(
    graph: InfraGraph,
    include_comments: bool,
    mark_spof: bool,
    version: str,
) -> IacExportResult:
    result = IacExportResult(format=ExportFormat.CLOUDFORMATION)
    blocks: list[str] = [_cfn_header(version)]
    spofs: list[str] = []

    for comp in graph.components.values():
        cid = _cfn_id(comp.id)
        fn = _CFN_DISPATCH.get(comp.type)
        if fn is None:
            result.warnings.append(
                f"Skipped '{comp.name}' ({comp.type.value}): CloudFormation export not supported for this type."
            )
            continue
        blocks.append(fn(comp, cid, graph, mark_spof))
        if mark_spof and _is_spof(comp, graph):
            spofs.append(comp.name)

    result.files["template.yaml"] = "".join(blocks)
    result.spof_components = spofs
    return result


# ---------------------------------------------------------------------------
# Kubernetes YAML generation
# ---------------------------------------------------------------------------


def _k8s_header(version: str) -> str:
    today = _today()
    return f"# Generated by FaultRay v{version} on {today}\n# Source: faultray iac-export --format kubernetes\n\n"


def _k8s_deployment(comp: Component, graph: InfraGraph, mark_spof: bool, include_comments: bool) -> str:
    name = _k8s_name(comp.id)
    image = _DEFAULT_K8S_IMAGE.get(comp.type, "alpine:3.19")
    port = _comp_port(comp)
    replicas = max(comp.replicas, 1)
    today = _today()
    parts: list[str] = []
    if mark_spof:
        parts.append(_spof_comment_k8s(comp, graph))
    parts.append('apiVersion: apps/v1\n')
    parts.append('kind: Deployment\n')
    parts.append('metadata:\n')
    parts.append(f'  name: {name}\n')
    parts.append('  labels:\n')
    parts.append(f'    app: {name}\n')
    parts.append('    managed-by: faultray\n')
    if include_comments:
        parts.append('  annotations:\n')
        parts.append(f'    faultray.io/discovered-at: "{today}"\n')
    parts.append('spec:\n')
    parts.append(f'  replicas: {replicas}\n')
    parts.append('  selector:\n')
    parts.append('    matchLabels:\n')
    parts.append(f'      app: {name}\n')
    parts.append('  template:\n')
    parts.append('    metadata:\n')
    parts.append('      labels:\n')
    parts.append(f'        app: {name}\n')
    parts.append('    spec:\n')
    parts.append('      containers:\n')
    parts.append(f'        - name: {name}\n')
    parts.append(f'          image: {image}\n')
    parts.append('          ports:\n')
    parts.append(f'            - containerPort: {port}\n')
    parts.append('---\n')
    return "".join(parts)


def _k8s_service(comp: Component) -> str:
    name = _k8s_name(comp.id)
    port = _comp_port(comp)
    svc_type = "LoadBalancer" if comp.type == ComponentType.LOAD_BALANCER else "ClusterIP"
    parts: list[str] = []
    parts.append('apiVersion: v1\n')
    parts.append('kind: Service\n')
    parts.append('metadata:\n')
    parts.append(f'  name: {name}\n')
    parts.append('  labels:\n')
    parts.append(f'    app: {name}\n')
    parts.append('    managed-by: faultray\n')
    parts.append('spec:\n')
    parts.append('  selector:\n')
    parts.append(f'    app: {name}\n')
    parts.append('  ports:\n')
    parts.append(f'    - port: {port}\n')
    parts.append(f'      targetPort: {port}\n')
    parts.append(f'  type: {svc_type}\n')
    parts.append('---\n')
    return "".join(parts)


_K8S_SKIP_TYPES: set[ComponentType] = {
    ComponentType.EXTERNAL_API,
    ComponentType.DNS,
    ComponentType.STORAGE,
    ComponentType.QUEUE,
}

_K8S_DB_TYPES: set[ComponentType] = {
    ComponentType.DATABASE,
    ComponentType.CACHE,
}


def _generate_kubernetes(
    graph: InfraGraph,
    include_comments: bool,
    mark_spof: bool,
    version: str,
) -> IacExportResult:
    result = IacExportResult(format=ExportFormat.KUBERNETES)
    spofs: list[str] = []
    blocks: list[str] = [_k8s_header(version)]

    for comp in graph.components.values():
        if comp.type in _K8S_SKIP_TYPES:
            result.warnings.append(
                f"'{comp.name}' ({comp.type.value}): typically not a K8s workload — skipped."
            )
            continue

        if comp.type in _K8S_DB_TYPES:
            result.warnings.append(
                f"'{comp.name}' ({comp.type.value}): stateful workload — generated as Deployment "
                f"(consider StatefulSet for production)."
            )

        blocks.append(_k8s_deployment(comp, graph, mark_spof, include_comments))
        blocks.append(_k8s_service(comp))
        if mark_spof and _is_spof(comp, graph):
            spofs.append(comp.name)

    result.files["manifests.yaml"] = "\n".join(blocks)
    result.spof_components = spofs
    return result


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


class IacExporter:
    """Export the current InfraGraph as-is to IaC files.

    Unlike :class:`faultray.remediation.iac_generator.IaCGenerator`, this
    class produces a *snapshot* of the infrastructure as it stands today, not
    a remediation plan.  SPOF annotations are embedded as comments so
    engineers can see resilience gaps inline.

    Usage::

        from faultray.iac.exporter import IacExporter, ExportFormat

        exporter = IacExporter(graph)
        result = exporter.export(
            fmt=ExportFormat.TERRAFORM,
            provider_region="us-east-1",
            include_comments=True,
            mark_spof=True,
        )
        # result.files: dict[filename, content]
        # result.spof_components: list of SPOF component names
    """

    def __init__(self, graph: InfraGraph) -> None:
        self._graph = graph

    def export(
        self,
        fmt: ExportFormat = ExportFormat.TERRAFORM,
        provider_region: str = "us-east-1",
        include_comments: bool = True,
        mark_spof: bool = True,
        version: str = "11.0.0",
    ) -> IacExportResult:
        """Generate as-is IaC code from the InfraGraph.

        Args:
            fmt: Target output format.
            provider_region: AWS region for Terraform/CloudFormation headers.
            include_comments: Include FaultRay discovery metadata as comments.
            mark_spof: Embed SPOF warning comments in affected resources.
            version: FaultRay version string to stamp in the file header.

        Returns:
            :class:`IacExportResult` with ``files``, ``warnings``, and
            ``spof_components`` populated.
        """
        if fmt == ExportFormat.TERRAFORM:
            return _generate_terraform(
                self._graph, provider_region, include_comments, mark_spof, version
            )
        if fmt == ExportFormat.CLOUDFORMATION:
            return _generate_cloudformation(
                self._graph, include_comments, mark_spof, version
            )
        if fmt == ExportFormat.KUBERNETES:
            return _generate_kubernetes(
                self._graph, include_comments, mark_spof, version
            )
        msg = f"Unsupported export format: {fmt}"
        raise ValueError(msg)

    def spof_summary(self) -> dict[str, list[str]]:
        """Return a dict mapping each SPOF component name to its dependent names."""
        summary: dict[str, list[str]] = {}
        for comp in self._graph.components.values():
            if _is_spof(comp, self._graph):
                deps = self._graph.get_dependents(comp.id)
                summary[comp.name] = [d.name for d in deps]
        return summary
