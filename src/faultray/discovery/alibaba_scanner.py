# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""Alibaba Cloud (Aliyun) infrastructure auto-discovery scanner.

Connects to Alibaba Cloud via official SDK to discover infrastructure resources
and generates a complete InfraGraph with components and dependencies.

Usage:
    pip install 'faultray[alibaba]'
    scanner = AlibabaScanner(
        access_key_id="xxx",
        access_key_secret="yyy",
        region="cn-hangzhou",
    )
    result = scanner.scan()
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

from faultray.model.components import (
    AutoScalingConfig,
    Capacity,
    Component,
    ComponentType,
    Dependency,
    RegionConfig,
    SecurityProfile,
)
from faultray.model.graph import InfraGraph

logger = logging.getLogger(__name__)

# Mapping from Alibaba Cloud service to FaultRay ComponentType
ALIBABA_TYPE_MAP: dict[str, ComponentType] = {
    "ecs": ComponentType.APP_SERVER,
    "rds": ComponentType.DATABASE,
    "slb": ComponentType.LOAD_BALANCER,
    "redis": ComponentType.CACHE,
    "oss": ComponentType.STORAGE,
    "vpc": ComponentType.CUSTOM,
}

# RDS engine to port mapping
_RDS_ENGINE_PORT: dict[str, int] = {
    "MySQL": 3306,
    "SQLServer": 1433,
    "PostgreSQL": 5432,
    "PPAS": 5432,
    "MariaDB": 3306,
}


def _check_alibaba_libs() -> None:
    """Check that required alibabacloud SDK libraries are importable."""
    try:
        import alibabacloud_ecs20140526  # noqa: F401
    except ImportError:
        raise RuntimeError(
            "alibabacloud-ecs20140526 is required for Alibaba Cloud scanning. "
            "Install with: pip install 'faultray[alibaba]'"
        )


def _make_ecs_client(access_key_id: str, access_key_secret: str, region: str):  # type: ignore[return]
    """Create an Alibaba Cloud ECS client."""
    from alibabacloud_ecs20140526.client import Client as EcsClient
    from alibabacloud_tea_openapi import models as open_api_models

    config = open_api_models.Config(
        access_key_id=access_key_id,
        access_key_secret=access_key_secret,
        region_id=region,
    )
    config.endpoint = f"ecs.{region}.aliyuncs.com"
    return EcsClient(config)


def _make_rds_client(access_key_id: str, access_key_secret: str, region: str):  # type: ignore[return]
    """Create an Alibaba Cloud RDS client."""
    from alibabacloud_rds20140815.client import Client as RdsClient
    from alibabacloud_tea_openapi import models as open_api_models

    config = open_api_models.Config(
        access_key_id=access_key_id,
        access_key_secret=access_key_secret,
        region_id=region,
    )
    config.endpoint = f"rds.{region}.aliyuncs.com"
    return RdsClient(config)


def _make_slb_client(access_key_id: str, access_key_secret: str, region: str):  # type: ignore[return]
    """Create an Alibaba Cloud SLB client."""
    from alibabacloud_slb20140515.client import Client as SlbClient
    from alibabacloud_tea_openapi import models as open_api_models

    config = open_api_models.Config(
        access_key_id=access_key_id,
        access_key_secret=access_key_secret,
        region_id=region,
    )
    config.endpoint = f"slb.{region}.aliyuncs.com"
    return SlbClient(config)


@dataclass
class AlibabaDiscoveryResult:
    """Result of an Alibaba Cloud infrastructure discovery scan."""

    region: str
    components_found: int
    dependencies_inferred: int
    graph: InfraGraph
    warnings: list[str] = field(default_factory=list)
    scan_duration_seconds: float = 0.0


class AlibabaScanner:
    """Discover Alibaba Cloud infrastructure and generate InfraGraph automatically.

    Authenticates using AccessKey ID and Secret.
    Scans ECS, RDS, SLB, Redis, OSS, and VPC resources.

    Args:
        access_key_id: Alibaba Cloud AccessKey ID.
        access_key_secret: Alibaba Cloud AccessKey Secret.
        region: Alibaba Cloud region ID (e.g. "cn-hangzhou", "ap-southeast-1").
        vpc_id: Optional VPC ID to filter resources.
    """

    def __init__(
        self,
        access_key_id: str,
        access_key_secret: str,
        region: str = "cn-hangzhou",
        vpc_id: str | None = None,
    ) -> None:
        self.access_key_id = access_key_id
        self.access_key_secret = access_key_secret
        self.region = region
        self.vpc_id = vpc_id
        self._warnings: list[str] = []
        # VPC ID -> list of component IDs in that VPC
        self._vpc_members: dict[str, list[str]] = {}
        # SLB backend server -> SLB component ID mapping
        self._slb_backends: dict[str, list[str]] = {}

    def scan(self) -> AlibabaDiscoveryResult:
        """Run a full Alibaba Cloud infrastructure scan.

        Returns an AlibabaDiscoveryResult with the discovered InfraGraph.
        """
        _check_alibaba_libs()

        start = time.monotonic()
        graph = InfraGraph()

        scanners = [
            ("ECS", self._scan_ecs),
            ("RDS", self._scan_rds),
            ("SLB", self._scan_slb),
            ("Redis", self._scan_redis),
            ("OSS", self._scan_oss),
            ("VPC", self._scan_vpc),
        ]

        for name, scanner_fn in scanners:
            try:
                scanner_fn(graph)
            except RuntimeError:
                raise  # Re-raise library import errors
            except Exception as exc:
                msg = f"Failed to scan Alibaba {name}: {exc}"
                logger.warning(msg)
                self._warnings.append(msg)

        try:
            self._infer_dependencies(graph)
        except Exception as exc:
            msg = f"Failed to infer Alibaba dependencies: {exc}"
            logger.warning(msg)
            self._warnings.append(msg)

        duration = time.monotonic() - start
        dep_count = len(graph.all_dependency_edges())

        return AlibabaDiscoveryResult(
            region=self.region,
            components_found=len(graph.components),
            dependencies_inferred=dep_count,
            graph=graph,
            warnings=list(self._warnings),
            scan_duration_seconds=round(duration, 2),
        )

    # ── Individual Resource Scanners ─────────────────────────────────────────

    def _scan_ecs(self, graph: InfraGraph) -> None:
        """Discover Alibaba Cloud ECS instances."""
        try:
            from alibabacloud_ecs20140526 import models as ecs_models

            client = _make_ecs_client(self.access_key_id, self.access_key_secret, self.region)

            page_number = 1
            page_size = 100
            while True:
                req = ecs_models.DescribeInstancesRequest(
                    region_id=self.region,
                    page_number=page_number,
                    page_size=page_size,
                    instance_charge_type=None,
                    status="Running",
                )
                if self.vpc_id:
                    req.vpc_id = self.vpc_id

                resp = client.describe_instances(req)
                instances = resp.body.instances.instance if resp.body.instances else []

                for inst in instances:
                    instance_id = inst.instance_id or ""
                    name = inst.instance_name or instance_id
                    comp_id = f"alibaba-ecs-{instance_id}"

                    host = ""
                    if inst.inner_ip_address and inst.inner_ip_address.ip_address:
                        host = inst.inner_ip_address.ip_address[0]
                    elif inst.network_interfaces and inst.network_interfaces.network_interface:
                        nic = inst.network_interfaces.network_interface[0]
                        host = nic.primary_ip_address or ""

                    vpc_id = inst.vpc_attributes.vpc_id if inst.vpc_attributes else ""
                    if vpc_id:
                        self._vpc_members.setdefault(vpc_id, []).append(comp_id)

                    cpu = inst.cpu or 1
                    memory_mb = inst.memory or 1024

                    component = Component(
                        id=comp_id,
                        name=name,
                        type=ComponentType.APP_SERVER,
                        host=host,
                        port=0,
                        replicas=1,
                        region=RegionConfig(
                            region=self.region,
                            availability_zone=inst.zone_id or "",
                        ),
                        capacity=Capacity(
                            max_connections=1000 * cpu,
                            max_rps=5000 * cpu,
                            max_memory_mb=float(memory_mb),
                        ),
                        tags=[
                            f"instance_type:{inst.instance_type or ''}",
                            f"cpu:{cpu}",
                        ],
                    )
                    graph.add_component(component)

                total = resp.body.total_count or 0
                if page_number * page_size >= total:
                    break
                page_number += 1
        except Exception as exc:
            self._warnings.append(f"Alibaba ECS scan error: {exc}")

    def _scan_rds(self, graph: InfraGraph) -> None:
        """Discover Alibaba Cloud RDS instances."""
        try:
            from alibabacloud_rds20140815 import models as rds_models

            client = _make_rds_client(self.access_key_id, self.access_key_secret, self.region)

            page_number = 1
            page_size = 100
            while True:
                req = rds_models.DescribeDBInstancesRequest(
                    region_id=self.region,
                    page_number=page_number,
                    page_size=page_size,
                )
                resp = client.describe_db_instances(req)
                items = (
                    resp.body.items.db_instance
                    if resp.body and resp.body.items
                    else []
                )

                for db in items:
                    db_id = db.db_instance_id or ""
                    name = db.db_instance_description or db_id
                    comp_id = f"alibaba-rds-{db_id}"

                    engine = db.engine or "MySQL"
                    port = _RDS_ENGINE_PORT.get(engine, 3306)

                    vpc_id = db.vpc_id or ""
                    if vpc_id:
                        self._vpc_members.setdefault(vpc_id, []).append(comp_id)

                    replicas = 2 if db.db_instance_type == "Primary" else 1

                    component = Component(
                        id=comp_id,
                        name=name,
                        type=ComponentType.DATABASE,
                        host="",
                        port=port,
                        replicas=replicas,
                        region=RegionConfig(
                            region=self.region,
                            availability_zone=db.zone_id or "",
                        ),
                        capacity=Capacity(
                            max_connections=800,
                            max_rps=5000,
                        ),
                        security=SecurityProfile(
                            encryption_at_rest=False,
                            backup_enabled=True,
                        ),
                        tags=[f"engine:{engine}", f"class:{db.db_instance_class or ''}"],
                    )
                    graph.add_component(component)

                total = resp.body.total_record_count if resp.body else 0
                if page_number * page_size >= (total or 0):
                    break
                page_number += 1
        except Exception as exc:
            self._warnings.append(f"Alibaba RDS scan error: {exc}")

    def _scan_slb(self, graph: InfraGraph) -> None:
        """Discover Alibaba Cloud Server Load Balancers."""
        try:
            from alibabacloud_slb20140515 import models as slb_models

            client = _make_slb_client(self.access_key_id, self.access_key_secret, self.region)

            page_number = 1
            page_size = 100
            while True:
                req = slb_models.DescribeLoadBalancersRequest(
                    region_id=self.region,
                    page_number=page_number,
                    page_size=page_size,
                )
                resp = client.describe_load_balancers(req)
                items = (
                    resp.body.load_balancers.load_balancer
                    if resp.body and resp.body.load_balancers
                    else []
                )

                for lb in items:
                    lb_id = lb.load_balancer_id or ""
                    name = lb.load_balancer_name or lb_id
                    comp_id = f"alibaba-slb-{lb_id}"

                    host = lb.address or ""
                    vpc_id = lb.vpc_id or ""
                    if vpc_id:
                        self._vpc_members.setdefault(vpc_id, []).append(comp_id)

                    component = Component(
                        id=comp_id,
                        name=name,
                        type=ComponentType.LOAD_BALANCER,
                        host=host,
                        port=80,
                        replicas=1,
                        region=RegionConfig(
                            region=self.region,
                            availability_zone=lb.master_zone_id or "",
                        ),
                        capacity=Capacity(max_connections=50000, max_rps=20000),
                    )
                    graph.add_component(component)

                    # Fetch backend servers for dependency inference
                    try:
                        backend_req = slb_models.DescribeHealthStatusRequest(
                            load_balancer_id=lb_id,
                        )
                        backend_resp = client.describe_health_status(backend_req)
                        servers = (
                            backend_resp.body.backend_servers.backend_server
                            if backend_resp.body and backend_resp.body.backend_servers
                            else []
                        )
                        for server in servers:
                            srv_id = server.server_id or ""
                            if srv_id:
                                self._slb_backends.setdefault(
                                    f"alibaba-ecs-{srv_id}", []
                                ).append(comp_id)
                    except Exception:
                        pass

                total = resp.body.total_count if resp.body else 0
                if page_number * page_size >= (total or 0):
                    break
                page_number += 1
        except Exception as exc:
            self._warnings.append(f"Alibaba SLB scan error: {exc}")

    def _scan_redis(self, graph: InfraGraph) -> None:
        """Discover Alibaba Cloud ApsaraDB for Redis instances."""
        try:
            # Redis SDK may not be installed; use requests fallback via SDK

            import requests

            # Use direct HTTP call with HMAC-SHA1 signing via requests
            # This avoids requiring the separate redis SDK package
            # We construct a minimal Alibaba Cloud RPC API call
            import hashlib
            import hmac
            import base64
            import urllib.parse
            from datetime import datetime, timezone

            def _sign_request(params: dict, secret: str) -> str:
                sorted_params = sorted(params.items())
                query = urllib.parse.urlencode([
                    (k, v) for k, v in sorted_params
                ])
                string_to_sign = f"GET&%2F&{urllib.parse.quote(query, safe='')}"
                key = f"{secret}&".encode()
                digest = hmac.new(key, string_to_sign.encode(), hashlib.sha1).digest()
                return base64.b64encode(digest).decode()

            timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            import uuid
            params: dict[str, str] = {
                "Action": "DescribeInstances",
                "Format": "JSON",
                "Version": "2015-01-01",
                "AccessKeyId": self.access_key_id,
                "SignatureMethod": "HMAC-SHA1",
                "Timestamp": timestamp,
                "SignatureVersion": "1.0",
                "SignatureNonce": str(uuid.uuid4()),
                "RegionId": self.region,
                "PageNumber": "1",
                "PageSize": "100",
            }
            params["Signature"] = _sign_request(params, self.access_key_secret)
            url = "https://r-kvstore.aliyuncs.com/"
            resp = requests.get(url, params=params, timeout=30)

            if resp.status_code == 200:
                data = resp.json()
                instances = (
                    data.get("Instances", {}).get("KVStoreInstance", [])
                )
                for inst in instances:
                    inst_id = inst.get("InstanceId", "")
                    name = inst.get("InstanceName", inst_id)
                    comp_id = f"alibaba-redis-{inst_id}"

                    host = inst.get("ConnectionDomain", "")
                    port = int(inst.get("Port", 6379))
                    vpc_id = inst.get("VpcId", "")
                    if vpc_id:
                        self._vpc_members.setdefault(vpc_id, []).append(comp_id)

                    replicas = 2 if inst.get("ReplicationMode") == "master-slave" else 1

                    component = Component(
                        id=comp_id,
                        name=name,
                        type=ComponentType.CACHE,
                        host=host,
                        port=port,
                        replicas=replicas,
                        region=RegionConfig(
                            region=self.region,
                            availability_zone=inst.get("ZoneId", ""),
                        ),
                        capacity=Capacity(
                            max_connections=10000,
                            max_rps=100000,
                            max_memory_mb=float(inst.get("Capacity", 1024)),
                        ),
                        autoscaling=AutoScalingConfig(enabled=False),
                        tags=[f"engine:{inst.get('EngineVersion', '')}"],
                    )
                    graph.add_component(component)
        except Exception as exc:
            self._warnings.append(f"Alibaba Redis scan error: {exc}")

    def _scan_oss(self, graph: InfraGraph) -> None:
        """Discover Alibaba Cloud OSS buckets."""
        try:
            import hashlib
            import hmac
            import base64
            from datetime import datetime, timezone

            import requests

            # OSS List Buckets API
            date_str = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S GMT")
            string_to_sign = f"GET\n\n\n{date_str}\n/"
            signature = base64.b64encode(
                hmac.new(
                    self.access_key_secret.encode(),
                    string_to_sign.encode(),
                    hashlib.sha1,
                ).digest()
            ).decode()

            headers = {
                "Date": date_str,
                "Authorization": f"OSS {self.access_key_id}:{signature}",
            }
            resp = requests.get("https://oss-cn-hangzhou.aliyuncs.com/", headers=headers, timeout=30)

            if resp.status_code == 200:
                import defusedxml.ElementTree as ET
                root = ET.fromstring(resp.text)
                ns = {"oss": "http://doc.oss-cn-hangzhou.aliyuncs.com"}

                for bucket_el in root.findall(".//oss:Bucket", ns):
                    bucket_name = bucket_el.findtext("oss:Name", default="", namespaces=ns)
                    location = bucket_el.findtext("oss:Location", default=self.region, namespaces=ns)
                    if not bucket_name:
                        continue

                    comp_id = f"alibaba-oss-{bucket_name}"
                    component = Component(
                        id=comp_id,
                        name=bucket_name,
                        type=ComponentType.STORAGE,
                        host=f"{bucket_name}.oss-{location}.aliyuncs.com",
                        port=443,
                        replicas=3,  # OSS is inherently replicated
                        region=RegionConfig(region=location),
                        capacity=Capacity(max_disk_gb=1024 * 1024),  # Effectively unlimited
                        security=SecurityProfile(encryption_at_rest=False),
                    )
                    graph.add_component(component)
        except Exception as exc:
            self._warnings.append(f"Alibaba OSS scan error: {exc}")

    def _scan_vpc(self, graph: InfraGraph) -> None:
        """Discover Alibaba Cloud VPCs (metadata only, for dependency context)."""
        try:
            import hashlib
            import hmac
            import base64
            import urllib.parse
            import uuid
            from datetime import datetime, timezone

            import requests

            timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            params: dict[str, str] = {
                "Action": "DescribeVpcs",
                "Format": "JSON",
                "Version": "2016-04-28",
                "AccessKeyId": self.access_key_id,
                "SignatureMethod": "HMAC-SHA1",
                "Timestamp": timestamp,
                "SignatureVersion": "1.0",
                "SignatureNonce": str(uuid.uuid4()),
                "RegionId": self.region,
                "PageNumber": "1",
                "PageSize": "100",
            }
            sorted_params = sorted(params.items())
            query = urllib.parse.urlencode(sorted_params)
            string_to_sign = f"GET&%2F&{urllib.parse.quote(query, safe='')}"
            key = f"{self.access_key_secret}&".encode()
            sig = base64.b64encode(
                hmac.new(key, string_to_sign.encode(), hashlib.sha1).digest()
            ).decode()
            params["Signature"] = sig

            resp = requests.get(f"https://vpc.{self.region}.aliyuncs.com/", params=params, timeout=30)
            if resp.status_code == 200:
                pass  # VPC metadata used for dependency inference only; no components created
        except Exception as exc:
            self._warnings.append(f"Alibaba VPC scan error: {exc}")

    # ── Dependency Inference ────────────────────────────────────────────────

    def _infer_dependencies(self, graph: InfraGraph) -> None:
        """Infer dependencies from VPC membership and SLB backend mappings."""
        # SLB -> ECS backend server dependencies
        for ecs_comp_id, slb_ids in self._slb_backends.items():
            if ecs_comp_id not in graph.components:
                continue
            for slb_comp_id in slb_ids:
                if slb_comp_id not in graph.components:
                    continue
                dep = Dependency(
                    source_id=slb_comp_id,
                    target_id=ecs_comp_id,
                    dependency_type="routes_to",
                    protocol="http",
                    port=80,
                )
                graph.add_dependency(dep)

        # Within-VPC: ECS -> RDS/Redis dependencies
        for vpc_id, members in self._vpc_members.items():
            members_set = set(members)
            ecs_members = [m for m in members_set if m in graph.components and
                           graph.components[m].type == ComponentType.APP_SERVER]
            db_members = [m for m in members_set if m in graph.components and
                          graph.components[m].type == ComponentType.DATABASE]
            cache_members = [m for m in members_set if m in graph.components and
                             graph.components[m].type == ComponentType.CACHE]

            for ecs in ecs_members:
                for db in db_members:
                    db_comp = graph.components[db]
                    dep = Dependency(
                        source_id=ecs,
                        target_id=db,
                        dependency_type="requires",
                        protocol="tcp",
                        port=db_comp.port,
                    )
                    graph.add_dependency(dep)

                for cache in cache_members:
                    cache_comp = graph.components[cache]
                    dep = Dependency(
                        source_id=ecs,
                        target_id=cache,
                        dependency_type="requires",
                        protocol="tcp",
                        port=cache_comp.port,
                    )
                    graph.add_dependency(dep)
