# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Business Source License 1.1. See LICENSE file for details.

"""AWS infrastructure auto-discovery scanner.

Connects to AWS via boto3 to discover all infrastructure resources and
generates a complete InfraGraph with components, dependencies, metrics,
security profiles, and cost profiles.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from faultray.errors import ExternalServiceError
from faultray.model.components import (
    AutoScalingConfig,
    Capacity,
    Component,
    ComponentType,
    Dependency,
    FailoverConfig,
    RegionConfig,
    ResourceMetrics,
    SecurityProfile,
)
from faultray.model.graph import InfraGraph

logger = logging.getLogger(__name__)

# Mapping from AWS service to FaultRay ComponentType
AWS_TYPE_MAP: dict[str, ComponentType] = {
    "ec2": ComponentType.APP_SERVER,
    "rds": ComponentType.DATABASE,
    "aurora": ComponentType.DATABASE,
    "elasticache": ComponentType.CACHE,
    "alb": ComponentType.LOAD_BALANCER,
    "nlb": ComponentType.LOAD_BALANCER,
    "ecs": ComponentType.APP_SERVER,
    "eks": ComponentType.APP_SERVER,
    "s3": ComponentType.STORAGE,
    "sqs": ComponentType.QUEUE,
    "cloudfront": ComponentType.LOAD_BALANCER,
    "route53": ComponentType.DNS,
    "lambda": ComponentType.APP_SERVER,
}

# Port-based dependency type heuristic
_DB_CACHE_PORTS = {3306, 5432, 6379, 11211, 27017, 5439}  # MySQL, PG, Redis, Memcached, Mongo, Redshift


def _is_critical_port(port: int) -> bool:
    """Return True if port typically indicates a database or cache service."""
    return port in _DB_CACHE_PORTS


def _boto3_session(region: str, profile: str | None = None):
    """Create a boto3 session, raising ExternalServiceError if boto3 is unavailable."""
    try:
        import boto3
    except ImportError:
        raise ExternalServiceError(
            "boto3 is required for AWS scanning. Install with: pip install boto3"
        )

    kwargs: dict = {"region_name": region}
    if profile:
        kwargs["profile_name"] = profile
    return boto3.Session(**kwargs)


@dataclass
class AWSDiscoveryResult:
    """Result of an AWS infrastructure discovery scan."""

    region: str
    components_found: int
    dependencies_inferred: int
    graph: InfraGraph
    warnings: list[str] = field(default_factory=list)
    scan_duration_seconds: float = 0.0


class AWSScanner:
    """Discover AWS infrastructure and generate InfraGraph automatically."""

    def __init__(self, region: str = "ap-northeast-1", profile: str | None = None):
        self.region = region
        self.profile = profile
        self._warnings: list[str] = []
        # Maps security-group-id -> list of component ids using that SG
        self._sg_to_components: dict[str, list[str]] = {}
        # Maps component id -> list of security group ids
        self._component_sgs: dict[str, list[str]] = {}
        # SG inbound rules: sg-id -> list of (source_sg, port)
        self._sg_inbound_rules: dict[str, list[tuple[str, int]]] = {}
        # ALB target group -> target component ids
        self._alb_targets: dict[str, list[str]] = {}
        # ECS env vars with endpoints
        self._ecs_endpoints: dict[str, list[str]] = {}
        # Route53 alias targets
        self._route53_aliases: dict[str, str] = {}
        # Instance-id -> component-id mapping
        self._instance_to_component: dict[str, str] = {}
        # Subnet-id -> is-private mapping
        self._subnet_private: dict[str, bool] = {}

    def scan(self) -> AWSDiscoveryResult:
        """Run a full AWS infrastructure scan.

        Returns an AWSDiscoveryResult with the discovered InfraGraph.
        """
        start = time.monotonic()
        graph = InfraGraph()

        scanners = [
            ("EC2", self._scan_ec2),
            ("RDS", self._scan_rds),
            ("ElastiCache", self._scan_elasticache),
            ("ALB/NLB", self._scan_alb_nlb),
            ("ECS", self._scan_ecs),
            ("S3", self._scan_s3),
            ("SQS", self._scan_sqs),
            ("CloudFront", self._scan_cloudfront),
            ("Route53", self._scan_route53),
            ("Lambda", self._scan_lambda),
        ]

        for name, scanner_fn in scanners:
            try:
                scanner_fn(graph)
            except ExternalServiceError:
                raise  # Re-raise boto3 import errors
            except Exception as exc:
                msg = f"Failed to scan {name}: {exc}"
                logger.warning(msg)
                self._warnings.append(msg)

        # Post-processing
        try:
            self._infer_dependencies(graph)
        except Exception as exc:
            msg = f"Failed to infer dependencies: {exc}"
            logger.warning(msg)
            self._warnings.append(msg)

        try:
            self._enrich_metrics(graph)
        except Exception as exc:
            msg = f"Failed to enrich metrics: {exc}"
            logger.warning(msg)
            self._warnings.append(msg)

        try:
            self._detect_security(graph)
        except Exception as exc:
            msg = f"Failed to detect security profiles: {exc}"
            logger.warning(msg)
            self._warnings.append(msg)

        duration = time.monotonic() - start
        dep_count = len(graph.all_dependency_edges())

        return AWSDiscoveryResult(
            region=self.region,
            components_found=len(graph.components),
            dependencies_inferred=dep_count,
            graph=graph,
            warnings=list(self._warnings),
            scan_duration_seconds=round(duration, 2),
        )

    # ── Individual Resource Scanners ─────────────────────────────────────────

    def _scan_ec2(self, graph: InfraGraph) -> None:
        """Discover EC2 instances."""
        session = _boto3_session(self.region, self.profile)
        ec2 = session.client("ec2")

        try:
            paginator = ec2.get_paginator("describe_instances")
            for page in paginator.paginate():
                for reservation in page.get("Reservations", []):
                    for inst in reservation.get("Instances", []):
                        state = inst.get("State", {}).get("Name", "")
                        if state != "running":
                            continue

                        instance_id = inst["InstanceId"]
                        name_tag = ""
                        for tag in inst.get("Tags", []):
                            if tag["Key"] == "Name":
                                name_tag = tag["Value"]
                                break

                        comp_id = f"ec2-{instance_id}"
                        self._instance_to_component[instance_id] = comp_id

                        # Track security groups
                        sg_ids = [sg["GroupId"] for sg in inst.get("SecurityGroups", [])]
                        self._component_sgs[comp_id] = sg_ids
                        for sg_id in sg_ids:
                            self._sg_to_components.setdefault(sg_id, []).append(comp_id)

                        # Determine AZ / subnet
                        az = inst.get("Placement", {}).get("AvailabilityZone", "")
                        inst.get("SubnetId", "")

                        component = Component(
                            id=comp_id,
                            name=name_tag or instance_id,
                            type=ComponentType.APP_SERVER,
                            host=inst.get("PrivateIpAddress", ""),
                            port=0,
                            replicas=1,
                            region=RegionConfig(
                                region=self.region,
                                availability_zone=az,
                            ),
                            capacity=Capacity(
                                max_connections=1000,
                                max_rps=5000,
                            ),
                            tags=[f"instance_type:{inst.get('InstanceType', '')}"],
                        )
                        graph.add_component(component)
        except Exception as exc:
            self._warnings.append(f"EC2 scan error: {exc}")

        # Collect security group rules
        try:
            sg_paginator = ec2.get_paginator("describe_security_groups")
            for page in sg_paginator.paginate():
                for sg in page.get("SecurityGroups", []):
                    sg_id = sg["GroupId"]
                    for rule in sg.get("IpPermissions", []):
                        from_port = rule.get("FromPort", 0)
                        for pair in rule.get("UserIdGroupPairs", []):
                            source_sg = pair.get("GroupId", "")
                            if source_sg:
                                self._sg_inbound_rules.setdefault(sg_id, []).append(
                                    (source_sg, from_port)
                                )
        except Exception as exc:
            self._warnings.append(f"Security group scan error: {exc}")

        # Collect subnet info for network segmentation detection
        try:
            rt_paginator = ec2.get_paginator("describe_route_tables")
            public_subnets: set[str] = set()
            for page in rt_paginator.paginate():
                for rt in page.get("RouteTables", []):
                    has_igw = any(
                        r.get("GatewayId", "").startswith("igw-")
                        for r in rt.get("Routes", [])
                    )
                    if has_igw:
                        for assoc in rt.get("Associations", []):
                            subnet = assoc.get("SubnetId", "")
                            if subnet:
                                public_subnets.add(subnet)

            sub_paginator = ec2.get_paginator("describe_subnets")
            for page in sub_paginator.paginate():
                for sub in page.get("Subnets", []):
                    sid = sub["SubnetId"]
                    self._subnet_private[sid] = sid not in public_subnets
        except Exception as exc:
            self._warnings.append(f"Subnet scan error: {exc}")

    def _scan_rds(self, graph: InfraGraph) -> None:
        """Discover RDS instances and Aurora clusters."""
        session = _boto3_session(self.region, self.profile)
        rds = session.client("rds")

        # Aurora clusters
        try:
            paginator = rds.get_paginator("describe_db_clusters")
            for page in paginator.paginate():
                for cluster in page.get("DBClusters", []):
                    cluster_id = cluster["DBClusterIdentifier"]
                    comp_id = f"rds-{cluster_id}"
                    members = cluster.get("DBClusterMembers", [])
                    num_members = len(members) if members else 1
                    az = cluster.get("AvailabilityZones", [])
                    multi_az = len(az) > 1

                    component = Component(
                        id=comp_id,
                        name=cluster_id,
                        type=ComponentType.DATABASE,
                        host=cluster.get("Endpoint", ""),
                        port=cluster.get("Port", 3306),
                        replicas=max(num_members, 1),
                        region=RegionConfig(
                            region=self.region,
                            availability_zone=",".join(az) if az else "",
                        ),
                        failover=FailoverConfig(
                            enabled=multi_az,
                            promotion_time_seconds=30.0 if multi_az else 0.0,
                        ),
                        security=SecurityProfile(
                            encryption_at_rest=cluster.get("StorageEncrypted", False),
                            backup_enabled=cluster.get("BackupRetentionPeriod", 0) > 0,
                            backup_frequency_hours=(
                                24.0 if cluster.get("BackupRetentionPeriod", 0) > 0 else 0.0
                            ),
                        ),
                        tags=["aurora", f"engine:{cluster.get('Engine', '')}"],
                    )

                    # Track SGs for dependency inference
                    sg_ids = [
                        sg["VpcSecurityGroupId"]
                        for sg in cluster.get("VpcSecurityGroups", [])
                    ]
                    self._component_sgs[comp_id] = sg_ids
                    for sg_id in sg_ids:
                        self._sg_to_components.setdefault(sg_id, []).append(comp_id)

                    graph.add_component(component)
        except Exception as exc:
            self._warnings.append(f"RDS cluster scan error: {exc}")

        # Standalone RDS instances (not part of Aurora cluster)
        try:
            paginator = rds.get_paginator("describe_db_instances")
            for page in paginator.paginate():
                for instance in page.get("DBInstances", []):
                    # Skip Aurora instances (already handled above)
                    if instance.get("DBClusterIdentifier"):
                        continue

                    db_id = instance["DBInstanceIdentifier"]
                    comp_id = f"rds-{db_id}"
                    multi_az = instance.get("MultiAZ", False)

                    component = Component(
                        id=comp_id,
                        name=db_id,
                        type=ComponentType.DATABASE,
                        host=instance.get("Endpoint", {}).get("Address", ""),
                        port=instance.get("Endpoint", {}).get("Port", 5432),
                        replicas=2 if multi_az else 1,
                        region=RegionConfig(
                            region=self.region,
                            availability_zone=instance.get("AvailabilityZone", ""),
                        ),
                        failover=FailoverConfig(
                            enabled=multi_az,
                            promotion_time_seconds=60.0 if multi_az else 0.0,
                        ),
                        security=SecurityProfile(
                            encryption_at_rest=instance.get("StorageEncrypted", False),
                            backup_enabled=instance.get("BackupRetentionPeriod", 0) > 0,
                            backup_frequency_hours=(
                                24.0
                                if instance.get("BackupRetentionPeriod", 0) > 0
                                else 0.0
                            ),
                        ),
                        tags=[f"engine:{instance.get('Engine', '')}"],
                    )

                    sg_ids = [
                        sg["VpcSecurityGroupId"]
                        for sg in instance.get("VpcSecurityGroups", [])
                    ]
                    self._component_sgs[comp_id] = sg_ids
                    for sg_id in sg_ids:
                        self._sg_to_components.setdefault(sg_id, []).append(comp_id)

                    graph.add_component(component)
        except Exception as exc:
            self._warnings.append(f"RDS instance scan error: {exc}")

    def _scan_elasticache(self, graph: InfraGraph) -> None:
        """Discover ElastiCache clusters and replication groups."""
        session = _boto3_session(self.region, self.profile)
        ec = session.client("elasticache")

        try:
            paginator = ec.get_paginator("describe_replication_groups")
            for page in paginator.paginate():
                for rg in page.get("ReplicationGroups", []):
                    rg_id = rg["ReplicationGroupId"]
                    comp_id = f"elasticache-{rg_id}"
                    node_groups = rg.get("NodeGroups", [])
                    num_nodes = sum(
                        len(ng.get("NodeGroupMembers", [])) for ng in node_groups
                    )
                    rg.get("MultiAZ", "") == "enabled"

                    component = Component(
                        id=comp_id,
                        name=rg_id,
                        type=ComponentType.CACHE,
                        host="",
                        port=6379,
                        replicas=max(num_nodes, 1),
                        failover=FailoverConfig(
                            enabled=rg.get("AutomaticFailover", "") == "enabled",
                            promotion_time_seconds=15.0,
                        ),
                        region=RegionConfig(region=self.region),
                        security=SecurityProfile(
                            encryption_at_rest=rg.get("AtRestEncryptionEnabled", False),
                            encryption_in_transit=rg.get("TransitEncryptionEnabled", False),
                        ),
                        tags=["redis"],
                    )
                    graph.add_component(component)
        except Exception as exc:
            self._warnings.append(f"ElastiCache replication group scan error: {exc}")

        # Standalone clusters
        try:
            paginator = ec.get_paginator("describe_cache_clusters")
            for page in paginator.paginate():
                for cluster in page.get("CacheClusters", []):
                    # Skip if part of a replication group (already scanned)
                    if cluster.get("ReplicationGroupId"):
                        continue

                    cluster_id = cluster["CacheClusterId"]
                    comp_id = f"elasticache-{cluster_id}"
                    num_nodes = cluster.get("NumCacheNodes", 1)

                    component = Component(
                        id=comp_id,
                        name=cluster_id,
                        type=ComponentType.CACHE,
                        host="",
                        port=cluster.get("ConfigurationEndpoint", {}).get("Port", 6379)
                        if cluster.get("ConfigurationEndpoint")
                        else 6379,
                        replicas=max(num_nodes, 1),
                        region=RegionConfig(region=self.region),
                        tags=[f"engine:{cluster.get('Engine', 'redis')}"],
                    )
                    graph.add_component(component)
        except Exception as exc:
            self._warnings.append(f"ElastiCache cluster scan error: {exc}")

    def _scan_alb_nlb(self, graph: InfraGraph) -> None:
        """Discover ALBs and NLBs, including target groups."""
        session = _boto3_session(self.region, self.profile)
        elbv2 = session.client("elbv2")

        lb_arns: list[str] = []

        try:
            paginator = elbv2.get_paginator("describe_load_balancers")
            for page in paginator.paginate():
                for lb in page.get("LoadBalancers", []):
                    lb_name = lb["LoadBalancerName"]
                    lb_type = lb.get("Type", "application")
                    lb_arn = lb["LoadBalancerArn"]
                    lb_arns.append(lb_arn)

                    azs = [az["ZoneName"] for az in lb.get("AvailabilityZones", [])]
                    multi_az = len(azs) > 1

                    comp_type_key = "alb" if lb_type == "application" else "nlb"
                    comp_id = f"{comp_type_key}-{lb_name}"

                    component = Component(
                        id=comp_id,
                        name=lb_name,
                        type=AWS_TYPE_MAP.get(comp_type_key, ComponentType.LOAD_BALANCER),
                        host=lb.get("DNSName", ""),
                        port=443,
                        replicas=len(azs) if azs else 1,
                        region=RegionConfig(
                            region=self.region,
                            availability_zone=",".join(azs),
                        ),
                        failover=FailoverConfig(enabled=multi_az),
                        capacity=Capacity(
                            max_connections=100000,
                            max_rps=100000,
                        ),
                        tags=[f"type:{lb_type}"],
                    )

                    sg_ids = lb.get("SecurityGroups", [])
                    self._component_sgs[comp_id] = sg_ids
                    for sg_id in sg_ids:
                        self._sg_to_components.setdefault(sg_id, []).append(comp_id)

                    graph.add_component(component)
        except Exception as exc:
            self._warnings.append(f"ALB/NLB scan error: {exc}")

        # Discover target groups and their targets
        for lb_arn in lb_arns:
            try:
                tg_resp = elbv2.describe_target_groups(LoadBalancerArn=lb_arn)
                for tg in tg_resp.get("TargetGroups", []):
                    tg_arn = tg["TargetGroupArn"]
                    try:
                        health_resp = elbv2.describe_target_health(TargetGroupArn=tg_arn)
                        for thd in health_resp.get("TargetHealthDescriptions", []):
                            target_id = thd.get("Target", {}).get("Id", "")
                            if target_id.startswith("i-"):
                                comp_id = self._instance_to_component.get(target_id)
                                if comp_id:
                                    lb_name = lb_arn.split("/")[-2] if "/" in lb_arn else lb_arn
                                    # Find the ALB component id
                                    for cid in graph.components:
                                        if lb_name in cid:
                                            self._alb_targets.setdefault(cid, []).append(comp_id)
                                            break
                    except Exception:
                        pass
            except Exception:
                pass

    def _scan_ecs(self, graph: InfraGraph) -> None:
        """Discover ECS clusters, services, and task definitions."""
        session = _boto3_session(self.region, self.profile)
        ecs = session.client("ecs")

        try:
            cluster_arns = []
            paginator = ecs.get_paginator("list_clusters")
            for page in paginator.paginate():
                cluster_arns.extend(page.get("clusterArns", []))

            for cluster_arn in cluster_arns:
                cluster_name = cluster_arn.split("/")[-1]

                # List services
                svc_arns: list[str] = []
                try:
                    svc_paginator = ecs.get_paginator("list_services")
                    for svc_page in svc_paginator.paginate(cluster=cluster_arn):
                        svc_arns.extend(svc_page.get("serviceArns", []))
                except Exception:
                    continue

                if not svc_arns:
                    continue

                # Describe services in batches of 10
                for i in range(0, len(svc_arns), 10):
                    batch = svc_arns[i : i + 10]
                    try:
                        svc_resp = ecs.describe_services(
                            cluster=cluster_arn, services=batch
                        )
                        for svc in svc_resp.get("services", []):
                            svc_name = svc["serviceName"]
                            comp_id = f"ecs-{cluster_name}-{svc_name}"
                            desired = svc.get("desiredCount", 1)
                            running = svc.get("runningCount", 0)

                            component = Component(
                                id=comp_id,
                                name=f"{cluster_name}/{svc_name}",
                                type=ComponentType.APP_SERVER,
                                replicas=max(desired, 1),
                                region=RegionConfig(region=self.region),
                                autoscaling=AutoScalingConfig(
                                    enabled=desired != running and desired > 1,
                                    min_replicas=1,
                                    max_replicas=max(desired * 2, 4),
                                ),
                                tags=["ecs", f"cluster:{cluster_name}"],
                            )
                            graph.add_component(component)

                            # Parse task definition for endpoint references
                            td_arn = svc.get("taskDefinition", "")
                            if td_arn:
                                self._parse_ecs_task_definition(ecs, td_arn, comp_id)
                    except Exception as exc:
                        self._warnings.append(
                            f"ECS service describe error in {cluster_name}: {exc}"
                        )
        except Exception as exc:
            self._warnings.append(f"ECS scan error: {exc}")

    def _parse_ecs_task_definition(self, ecs_client, td_arn: str, comp_id: str) -> None:
        """Parse ECS task definition for DB/cache endpoint environment variables."""
        try:
            resp = ecs_client.describe_task_definition(taskDefinition=td_arn)
            td = resp.get("taskDefinition", {})
            for container in td.get("containerDefinitions", []):
                for env in container.get("environment", []):
                    val = env.get("value", "")
                    # Look for RDS/Redis/ElastiCache endpoints
                    if any(
                        keyword in val.lower()
                        for keyword in [
                            ".rds.amazonaws.com",
                            ".cache.amazonaws.com",
                            "redis://",
                            "postgresql://",
                            "mysql://",
                        ]
                    ):
                        self._ecs_endpoints.setdefault(comp_id, []).append(val)
        except Exception:
            pass

    def _scan_s3(self, graph: InfraGraph) -> None:
        """Discover S3 buckets."""
        session = _boto3_session(self.region, self.profile)
        s3 = session.client("s3")

        try:
            resp = s3.list_buckets()
            for bucket in resp.get("Buckets", []):
                bucket_name = bucket["Name"]
                comp_id = f"s3-{bucket_name}"

                # Try to get bucket location
                try:
                    loc = s3.get_bucket_location(Bucket=bucket_name)
                    bucket_region = loc.get("LocationConstraint") or "us-east-1"
                except Exception:
                    bucket_region = self.region

                # Only include buckets in the target region
                if bucket_region != self.region:
                    continue

                # Check encryption
                encrypted = False
                try:
                    enc_resp = s3.get_bucket_encryption(Bucket=bucket_name)
                    rules = enc_resp.get("ServerSideEncryptionConfiguration", {}).get(
                        "Rules", []
                    )
                    encrypted = len(rules) > 0
                except Exception:
                    pass

                # Check versioning
                versioning = False
                try:
                    ver_resp = s3.get_bucket_versioning(Bucket=bucket_name)
                    versioning = ver_resp.get("Status") == "Enabled"
                except Exception:
                    pass

                component = Component(
                    id=comp_id,
                    name=bucket_name,
                    type=ComponentType.STORAGE,
                    replicas=3,  # S3 is inherently replicated
                    region=RegionConfig(region=bucket_region),
                    security=SecurityProfile(
                        encryption_at_rest=encrypted,
                        backup_enabled=versioning,
                    ),
                    tags=["s3"],
                )
                graph.add_component(component)
        except Exception as exc:
            self._warnings.append(f"S3 scan error: {exc}")

    def _scan_sqs(self, graph: InfraGraph) -> None:
        """Discover SQS queues."""
        session = _boto3_session(self.region, self.profile)
        sqs = session.client("sqs")

        try:
            resp = sqs.list_queues()
            for url in resp.get("QueueUrls", []):
                queue_name = url.split("/")[-1]
                comp_id = f"sqs-{queue_name}"

                # Get queue attributes
                try:
                    attr_resp = sqs.get_queue_attributes(
                        QueueUrl=url,
                        AttributeNames=["All"],
                    )
                    attrs = attr_resp.get("Attributes", {})
                except Exception:
                    attrs = {}

                encrypted = bool(attrs.get("KmsMasterKeyId"))
                approx_messages = int(attrs.get("ApproximateNumberOfMessages", 0))

                component = Component(
                    id=comp_id,
                    name=queue_name,
                    type=ComponentType.QUEUE,
                    replicas=3,  # SQS is regionally replicated
                    region=RegionConfig(region=self.region),
                    security=SecurityProfile(encryption_at_rest=encrypted),
                    metrics=ResourceMetrics(
                        network_connections=approx_messages,
                    ),
                    tags=["sqs"],
                )
                graph.add_component(component)
        except Exception as exc:
            self._warnings.append(f"SQS scan error: {exc}")

    def _scan_cloudfront(self, graph: InfraGraph) -> None:
        """Discover CloudFront distributions."""
        session = _boto3_session(self.region, self.profile)
        cf = session.client("cloudfront")

        try:
            paginator = cf.get_paginator("list_distributions")
            for page in paginator.paginate():
                dist_list = page.get("DistributionList", {})
                for dist in dist_list.get("Items", []):
                    dist_id = dist["Id"]
                    comp_id = f"cloudfront-{dist_id}"
                    domain = dist.get("DomainName", "")

                    waf_acl = dist.get("WebACLId", "")

                    component = Component(
                        id=comp_id,
                        name=f"CloudFront {dist_id}",
                        type=ComponentType.LOAD_BALANCER,
                        host=domain,
                        port=443,
                        replicas=3,  # CloudFront is globally distributed
                        region=RegionConfig(region="global"),
                        security=SecurityProfile(
                            encryption_in_transit=True,  # CloudFront always uses HTTPS edge
                            waf_protected=bool(waf_acl),
                        ),
                        tags=["cloudfront"],
                    )
                    graph.add_component(component)
        except Exception as exc:
            self._warnings.append(f"CloudFront scan error: {exc}")

    def _scan_route53(self, graph: InfraGraph) -> None:
        """Discover Route53 hosted zones and records."""
        session = _boto3_session(self.region, self.profile)
        r53 = session.client("route53")

        try:
            hz_resp = r53.list_hosted_zones()
            for zone in hz_resp.get("HostedZones", []):
                zone_id = zone["Id"].split("/")[-1]
                zone_name = zone["Name"].rstrip(".")

                comp_id = f"route53-{zone_id}"
                component = Component(
                    id=comp_id,
                    name=f"DNS: {zone_name}",
                    type=ComponentType.DNS,
                    replicas=4,  # Route53 is globally redundant
                    region=RegionConfig(region="global"),
                    tags=["route53", f"zone:{zone_name}"],
                )
                graph.add_component(component)

                # Check alias targets for dependency inference
                try:
                    rr_resp = r53.list_resource_record_sets(HostedZoneId=zone_id)
                    for rr in rr_resp.get("ResourceRecordSets", []):
                        alias = rr.get("AliasTarget", {})
                        dns_name = alias.get("DNSName", "")
                        if dns_name:
                            self._route53_aliases[comp_id] = dns_name
                except Exception:
                    pass
        except Exception as exc:
            self._warnings.append(f"Route53 scan error: {exc}")

    def _scan_lambda(self, graph: InfraGraph) -> None:
        """Discover Lambda functions."""
        session = _boto3_session(self.region, self.profile)
        lam = session.client("lambda")

        try:
            paginator = lam.get_paginator("list_functions")
            for page in paginator.paginate():
                for fn in page.get("Functions", []):
                    fn_name = fn["FunctionName"]
                    comp_id = f"lambda-{fn_name}"
                    memory_mb = fn.get("MemorySize", 128)
                    runtime = fn.get("Runtime", "")

                    component = Component(
                        id=comp_id,
                        name=fn_name,
                        type=ComponentType.APP_SERVER,
                        replicas=1,
                        region=RegionConfig(region=self.region),
                        capacity=Capacity(
                            max_memory_mb=float(memory_mb),
                            timeout_seconds=float(fn.get("Timeout", 3)),
                        ),
                        autoscaling=AutoScalingConfig(
                            enabled=True,
                            min_replicas=0,
                            max_replicas=1000,
                        ),
                        tags=["lambda", f"runtime:{runtime}"],
                    )

                    # Track VPC config for SG-based dependency inference
                    vpc_cfg = fn.get("VpcConfig", {})
                    sg_ids = vpc_cfg.get("SecurityGroupIds", [])
                    if sg_ids:
                        self._component_sgs[comp_id] = sg_ids
                        for sg_id in sg_ids:
                            self._sg_to_components.setdefault(sg_id, []).append(comp_id)

                    graph.add_component(component)
        except Exception as exc:
            self._warnings.append(f"Lambda scan error: {exc}")

    # ── Dependency Inference ─────────────────────────────────────────────────

    def _infer_dependencies(self, graph: InfraGraph) -> None:
        """Infer dependencies from security groups, target groups, ECS env vars, and Route53."""
        existing_edges: set[tuple[str, str]] = set()

        # 1. Security group based inference
        # If sg-A allows inbound from sg-B on port X:
        #   Components with sg-B depend on components with sg-A
        for target_sg, rules in self._sg_inbound_rules.items():
            target_comps = self._sg_to_components.get(target_sg, [])
            for source_sg, port in rules:
                source_comps = self._sg_to_components.get(source_sg, [])
                for src_comp in source_comps:
                    for tgt_comp in target_comps:
                        if src_comp == tgt_comp:
                            continue
                        edge_key = (src_comp, tgt_comp)
                        if edge_key in existing_edges:
                            continue
                        if src_comp not in graph.components or tgt_comp not in graph.components:
                            continue
                        existing_edges.add(edge_key)
                        dep_type = "requires" if _is_critical_port(port) else "optional"
                        dep = Dependency(
                            source_id=src_comp,
                            target_id=tgt_comp,
                            dependency_type=dep_type,
                            protocol="tcp",
                            port=port,
                        )
                        graph.add_dependency(dep)

        # 2. ALB target group dependencies
        for alb_comp_id, target_comp_ids in self._alb_targets.items():
            for target_id in target_comp_ids:
                edge_key = (alb_comp_id, target_id)
                if edge_key in existing_edges:
                    continue
                if alb_comp_id not in graph.components or target_id not in graph.components:
                    continue
                existing_edges.add(edge_key)
                dep = Dependency(
                    source_id=alb_comp_id,
                    target_id=target_id,
                    dependency_type="requires",
                    protocol="http",
                    port=80,
                )
                graph.add_dependency(dep)

        # 3. ECS task definition endpoint references
        for ecs_comp_id, endpoints in self._ecs_endpoints.items():
            for endpoint in endpoints:
                endpoint_lower = endpoint.lower()
                for comp_id, comp in graph.components.items():
                    if comp_id == ecs_comp_id:
                        continue
                    # Match RDS/ElastiCache endpoints against component hosts
                    if comp.host and comp.host.lower() in endpoint_lower:
                        edge_key = (ecs_comp_id, comp_id)
                        if edge_key not in existing_edges:
                            existing_edges.add(edge_key)
                            dep = Dependency(
                                source_id=ecs_comp_id,
                                target_id=comp_id,
                                dependency_type="requires",
                                protocol="tcp",
                                port=comp.port,
                            )
                            graph.add_dependency(dep)

        # 4. Route53 alias dependencies
        for dns_comp_id, alias_dns in self._route53_aliases.items():
            alias_lower = alias_dns.lower().rstrip(".")
            for comp_id, comp in graph.components.items():
                if comp_id == dns_comp_id:
                    continue
                if comp.host and comp.host.lower() in alias_lower:
                    edge_key = (dns_comp_id, comp_id)
                    if edge_key not in existing_edges:
                        existing_edges.add(edge_key)
                        dep = Dependency(
                            source_id=dns_comp_id,
                            target_id=comp_id,
                            dependency_type="requires",
                            protocol="dns",
                            port=0,
                        )
                        graph.add_dependency(dep)

    # ── Metric Enrichment ────────────────────────────────────────────────────

    def _enrich_metrics(self, graph: InfraGraph) -> None:
        """Enrich components with CloudWatch metrics."""
        session = _boto3_session(self.region, self.profile)
        cw = session.client("cloudwatch")

        for comp_id, comp in graph.components.items():
            try:
                if comp_id.startswith("ec2-"):
                    instance_id = comp_id.replace("ec2-", "", 1)
                    self._fetch_ec2_metrics(cw, instance_id, comp)
                elif comp_id.startswith("rds-"):
                    db_id = comp_id.replace("rds-", "", 1)
                    self._fetch_rds_metrics(cw, db_id, comp)
            except Exception:
                pass

    def _fetch_ec2_metrics(self, cw, instance_id: str, comp: Component) -> None:
        """Fetch CPU utilization from CloudWatch for an EC2 instance."""
        import datetime

        end = datetime.datetime.now(datetime.timezone.utc)
        start = end - datetime.timedelta(hours=1)

        resp = cw.get_metric_statistics(
            Namespace="AWS/EC2",
            MetricName="CPUUtilization",
            Dimensions=[{"Name": "InstanceId", "Value": instance_id}],
            StartTime=start,
            EndTime=end,
            Period=3600,
            Statistics=["Average"],
        )
        datapoints = resp.get("Datapoints", [])
        if datapoints:
            avg_cpu = datapoints[0].get("Average", 0.0)
            comp.metrics.cpu_percent = avg_cpu

    def _fetch_rds_metrics(self, cw, db_id: str, comp: Component) -> None:
        """Fetch CPU utilization from CloudWatch for an RDS instance."""
        import datetime

        end = datetime.datetime.now(datetime.timezone.utc)
        start = end - datetime.timedelta(hours=1)

        resp = cw.get_metric_statistics(
            Namespace="AWS/RDS",
            MetricName="CPUUtilization",
            Dimensions=[{"Name": "DBInstanceIdentifier", "Value": db_id}],
            StartTime=start,
            EndTime=end,
            Period=3600,
            Statistics=["Average"],
        )
        datapoints = resp.get("Datapoints", [])
        if datapoints:
            avg_cpu = datapoints[0].get("Average", 0.0)
            comp.metrics.cpu_percent = avg_cpu

    # ── Security Profile Detection ───────────────────────────────────────────

    def _detect_security(self, graph: InfraGraph) -> None:
        """Detect and enrich security profiles for all components."""
        session = _boto3_session(self.region, self.profile)

        # Check WAF associations
        waf_protected_arns: set[str] = set()
        try:
            waf = session.client("wafv2")
            for scope in ["REGIONAL", "CLOUDFRONT"]:
                try:
                    acl_resp = waf.list_web_acls(Scope=scope)
                    for acl in acl_resp.get("WebACLs", []):
                        acl_arn = acl["ARN"]
                        try:
                            res_resp = waf.list_resources_for_web_acl(WebACLArn=acl_arn)
                            waf_protected_arns.update(
                                res_resp.get("ResourceArns", [])
                            )
                        except Exception:
                            pass
                        # Check for rate-based rules
                        try:
                            detail = waf.get_web_acl(
                                Name=acl["Name"], Scope=scope, Id=acl["Id"]
                            )
                            rules = detail.get("WebACL", {}).get("Rules", [])
                            for rule in rules:
                                stmt = rule.get("Statement", {})
                                if "RateBasedStatement" in stmt:
                                    for arn in waf_protected_arns:
                                        # Mark rate limiting for WAF-protected resources
                                        for comp in graph.components.values():
                                            if comp.host and comp.host in arn:
                                                comp.security.rate_limiting = True
                        except Exception:
                            pass
                except Exception:
                    pass
        except Exception as exc:
            self._warnings.append(f"WAF scan error: {exc}")

        # Apply WAF protection to components
        for comp in graph.components.values():
            if any(comp.host and comp.host in arn for arn in waf_protected_arns):
                comp.security.waf_protected = True

        # Check network segmentation using subnet info
        for comp_id, comp in graph.components.items():
            if comp_id.startswith("ec2-"):
                comp_id.replace("ec2-", "", 1)
                # Check if the component's subnet is private
                for subnet_id, is_private in self._subnet_private.items():
                    if is_private:
                        comp.security.network_segmented = True
                        break

        # Encryption in transit: check if port is 443 or has TLS configured
        for comp in graph.components.values():
            if comp.port == 443:
                comp.security.encryption_in_transit = True

        # VPC Flow Logs / CloudTrail check
        try:
            ec2 = session.client("ec2")
            flow_resp = ec2.describe_flow_logs()
            has_flow_logs = len(flow_resp.get("FlowLogs", [])) > 0
            if has_flow_logs:
                for comp in graph.components.values():
                    comp.security.log_enabled = True
        except Exception:
            pass


def export_yaml(graph: InfraGraph, path: Path) -> None:
    """Export an InfraGraph to FaultRay YAML format.

    Generates a YAML file compatible with ``faultray load``.

    Args:
        graph: The InfraGraph to export.
        path: File path to write the YAML output to.
    """
    components_list = []
    for comp in graph.components.values():
        entry: dict = {
            "id": comp.id,
            "name": comp.name,
            "type": comp.type.value,
        }
        if comp.host:
            entry["host"] = comp.host
        if comp.port:
            entry["port"] = comp.port
        if comp.replicas != 1:
            entry["replicas"] = comp.replicas

        # Capacity (only non-default)
        cap = comp.capacity
        cap_dict: dict = {}
        if cap.max_connections != 1000:
            cap_dict["max_connections"] = cap.max_connections
        if cap.max_rps != 5000:
            cap_dict["max_rps"] = cap.max_rps
        if cap.connection_pool_size != 100:
            cap_dict["connection_pool_size"] = cap.connection_pool_size
        if cap.max_memory_mb != 8192:
            cap_dict["max_memory_mb"] = cap.max_memory_mb
        if cap.timeout_seconds != 30.0:
            cap_dict["timeout_seconds"] = cap.timeout_seconds
        if cap_dict:
            entry["capacity"] = cap_dict

        # Metrics (only non-zero)
        m = comp.metrics
        met_dict: dict = {}
        if m.cpu_percent:
            met_dict["cpu_percent"] = round(m.cpu_percent, 1)
        if m.memory_percent:
            met_dict["memory_percent"] = round(m.memory_percent, 1)
        if m.disk_percent:
            met_dict["disk_percent"] = round(m.disk_percent, 1)
        if m.network_connections:
            met_dict["network_connections"] = m.network_connections
        if met_dict:
            entry["metrics"] = met_dict

        # Autoscaling
        if comp.autoscaling.enabled:
            entry["autoscaling"] = {
                "enabled": True,
                "min_replicas": comp.autoscaling.min_replicas,
                "max_replicas": comp.autoscaling.max_replicas,
            }

        # Failover
        if comp.failover.enabled:
            entry["failover"] = {
                "enabled": True,
                "promotion_time_seconds": comp.failover.promotion_time_seconds,
            }

        # Region
        reg = comp.region
        if reg.region or reg.availability_zone:
            reg_dict: dict = {}
            if reg.region:
                reg_dict["region"] = reg.region
            if reg.availability_zone:
                reg_dict["availability_zone"] = reg.availability_zone
            entry["region"] = reg_dict

        # Security
        sec = comp.security
        sec_dict: dict = {}
        for field_name in [
            "encryption_at_rest",
            "encryption_in_transit",
            "waf_protected",
            "rate_limiting",
            "network_segmented",
            "backup_enabled",
            "log_enabled",
        ]:
            val = getattr(sec, field_name, False)
            if val:
                sec_dict[field_name] = val
        if sec_dict:
            entry["security"] = sec_dict

        # Tags
        if comp.tags:
            entry["tags"] = comp.tags

        components_list.append(entry)

    # Dependencies
    deps_list = []
    for dep_edge in graph.all_dependency_edges():
        dep_entry: dict = {
            "source": dep_edge.source_id,
            "target": dep_edge.target_id,
        }
        if dep_edge.dependency_type != "requires":
            dep_entry["type"] = dep_edge.dependency_type
        if dep_edge.protocol:
            dep_entry["protocol"] = dep_edge.protocol
        if dep_edge.port:
            dep_entry["port"] = dep_edge.port
        deps_list.append(dep_entry)

    output: dict = {"components": components_list}
    if deps_list:
        output["dependencies"] = deps_list

    path.write_text(yaml.dump(output, default_flow_style=False, sort_keys=False, allow_unicode=True))
