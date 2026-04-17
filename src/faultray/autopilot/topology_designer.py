# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""Topology Designer: RequirementsSpecからInfraGraphを生成する。

テンプレートベース + ルール適用。外部APIに依存しない。
"""

from __future__ import annotations

from faultray.autopilot.requirements_parser import ComponentSpec, RequirementsSpec
from faultray.model.components import (
    AutoScalingConfig,
    Component,
    ComponentType,
    Dependency,
    FailoverConfig,
    RegionConfig,
)
from faultray.model.graph import InfraGraph


# ---------------------------------------------------------------------------
# Role → ComponentType mapping
# ---------------------------------------------------------------------------

_ROLE_TO_COMPONENT_TYPE: dict[str, ComponentType] = {
    "frontend": ComponentType.WEB_SERVER,
    "api": ComponentType.APP_SERVER,
    "database": ComponentType.DATABASE,
    "cache": ComponentType.CACHE,
    "queue": ComponentType.QUEUE,
    "storage": ComponentType.STORAGE,
    "cdn": ComponentType.LOAD_BALANCER,   # No CDN type; use LOAD_BALANCER as closest
    "lb": ComponentType.LOAD_BALANCER,
    "search": ComponentType.APP_SERVER,
}

# Technology → service label (used for YAML / Terraform naming)
_TECH_SERVICE_LABEL: dict[str, str] = {
    "React": "S3 + CloudFront",
    "Vue.js": "S3 + CloudFront",
    "Next.js": "ECS Fargate",
    "Node.js": "ECS Fargate",
    "Express": "ECS Fargate",
    "FastAPI": "ECS Fargate",
    "Django": "ECS Fargate",
    "Rails": "ECS Fargate",
    "Spring Boot": "ECS Fargate",
    "Flask": "ECS Fargate",
    "Go": "ECS Fargate",
    "PostgreSQL": "RDS PostgreSQL",
    "MySQL": "RDS MySQL",
    "Aurora": "Aurora",
    "DynamoDB": "DynamoDB",
    "MongoDB": "DocumentDB",
    "Redis": "ElastiCache Redis",
    "Memcached": "ElastiCache Memcached",
    "ElastiCache": "ElastiCache Redis",
    "SQS": "SQS",
    "Kafka": "MSK",
    "Kinesis": "Kinesis",
    "S3": "S3",
    "CloudFront": "CloudFront",
    "Elasticsearch": "OpenSearch",
    "OpenSearch": "OpenSearch",
    "RDS": "RDS PostgreSQL",
}


# ---------------------------------------------------------------------------
# TopologyDesigner
# ---------------------------------------------------------------------------


class TopologyDesigner:
    """Generate InfraGraph from RequirementsSpec.

    Applies topology rules:
    - availability >= 99.9% → multi-AZ (replicas=2, failover enabled)
    - availability >= 99.99% → multi-region hint in component tags
    - database + HA → RDS Multi-AZ (failover.enabled=True)
    - High traffic → autoscaling enabled on app servers
    - Always add ALB in front of app servers for web_app/api types
    """

    def design(self, spec: RequirementsSpec) -> InfraGraph:
        """Generate InfraGraph from RequirementsSpec."""
        graph = InfraGraph()
        multi_az = spec.multi_az
        high_traffic = spec.traffic_scale in ("high", "very_high")

        # Track created component IDs for wiring dependencies
        component_ids: dict[str, str] = {}  # role → component_id

        # Always add ALB for web_app and api types (unless CDN handles it)
        needs_alb = spec.app_type in ("web_app", "api", "microservices")
        cdn_spec = next((c for c in spec.components if c.role == "cdn"), None)

        if needs_alb:
            alb = self._make_alb(spec, multi_az)
            graph.add_component(alb)
            component_ids["lb"] = alb.id

        # Create component for each spec
        for comp_spec in spec.components:
            if comp_spec.role == "cdn":
                comp = self._make_cdn(spec)
            else:
                comp = self._make_component(comp_spec, spec, multi_az, high_traffic)
            graph.add_component(comp)
            component_ids[comp_spec.role] = comp.id

        # Wire dependencies
        self._wire_dependencies(graph, component_ids, spec, cdn_spec)

        return graph

    # ------------------------------------------------------------------
    # Component factories
    # ------------------------------------------------------------------

    def _make_alb(self, spec: RequirementsSpec, multi_az: bool) -> Component:
        replicas = 2 if multi_az else 1
        return Component(
            id="alb",
            name="Application Load Balancer",
            type=ComponentType.LOAD_BALANCER,
            host=f"alb.{spec.region}.elb.amazonaws.com",
            port=443,
            replicas=replicas,
            region=RegionConfig(region=spec.region),
            tags=["aws", "alb", "load_balancer"],
        )

    def _make_cdn(self, spec: RequirementsSpec) -> Component:
        return Component(
            id="cloudfront",
            name="CloudFront CDN",
            type=ComponentType.LOAD_BALANCER,
            host="d1234abcd.cloudfront.net",
            port=443,
            replicas=1,
            region=RegionConfig(region="us-east-1"),  # CloudFront is global
            tags=["aws", "cloudfront", "cdn"],
        )

    def _make_component(
        self,
        comp_spec: ComponentSpec,
        spec: RequirementsSpec,
        multi_az: bool,
        high_traffic: bool,
    ) -> Component:
        comp_type = _ROLE_TO_COMPONENT_TYPE.get(comp_spec.role, ComponentType.APP_SERVER)
        service_label = _TECH_SERVICE_LABEL.get(comp_spec.technology, comp_spec.technology)

        # Replica count
        if comp_spec.role == "database":
            replicas = 2 if multi_az else 1  # primary + replica
        elif comp_spec.role in ("cache",):
            replicas = 2 if multi_az else 1
        elif comp_spec.role in ("api", "frontend") and multi_az:
            replicas = 2
        else:
            replicas = 1

        # Autoscaling for app servers
        autoscaling = AutoScalingConfig(
            enabled=False,
            min_replicas=replicas,
            max_replicas=replicas,
        )
        if comp_spec.scaling == "auto" or (high_traffic and comp_spec.role == "api"):
            max_r = 10 if spec.traffic_scale == "very_high" else 4
            autoscaling = AutoScalingConfig(
                enabled=True,
                min_replicas=max(2 if multi_az else 1, replicas),
                max_replicas=max_r,
                scale_up_threshold=70.0,
                scale_down_threshold=30.0,
            )

        # Failover for databases and caches
        failover = FailoverConfig(enabled=False)
        if comp_spec.role == "database" and multi_az:
            failover = FailoverConfig(
                enabled=True,
                promotion_time_seconds=30.0,
                health_check_interval_seconds=10.0,
                failover_threshold=3,
            )
        elif comp_spec.role == "cache" and multi_az:
            failover = FailoverConfig(
                enabled=True,
                promotion_time_seconds=15.0,
                health_check_interval_seconds=5.0,
                failover_threshold=2,
            )

        # Port defaults per role
        port_map = {
            "frontend": 443,
            "api": 3000,
            "database": 5432,
            "cache": 6379,
            "queue": 5672,
            "storage": 443,
            "search": 9200,
        }
        port = port_map.get(comp_spec.role, 8080)
        if comp_spec.technology in ("MySQL", "RDS MySQL"):
            port = 3306
        elif comp_spec.technology == "Redis":
            port = 6379
        elif comp_spec.technology in ("SQS", "S3", "CloudFront"):
            port = 443

        tags = ["aws", comp_spec.role, comp_spec.technology.lower().replace(" ", "_")]
        if multi_az:
            tags.append("multi_az")
        if spec.multi_region:
            tags.append("multi_region")

        return Component(
            id=comp_spec.role,
            name=f"{comp_spec.technology} ({service_label})",
            type=comp_type,
            host=f"{comp_spec.role}.internal",
            port=port,
            replicas=replicas,
            autoscaling=autoscaling,
            failover=failover,
            region=RegionConfig(region=spec.region),
            tags=tags,
        )

    # ------------------------------------------------------------------
    # Dependency wiring
    # ------------------------------------------------------------------

    def _wire_dependencies(
        self,
        graph: InfraGraph,
        ids: dict[str, str],
        spec: RequirementsSpec,
        cdn_spec: ComponentSpec | None,
    ) -> None:
        """Add dependency edges based on component roles."""

        def _add(src: str, tgt: str, dep_type: str = "requires", weight: float = 1.0) -> None:
            if src in ids and tgt in ids:
                graph.add_dependency(
                    Dependency(
                        source_id=ids[src],
                        target_id=ids[tgt],
                        dependency_type=dep_type,
                        weight=weight,
                    )
                )

        # CDN → ALB (or frontend)
        if cdn_spec:
            if "lb" in ids:
                _add("cdn", "lb")
            elif "frontend" in ids:
                _add("cdn", "frontend")

        # ALB → frontend or api
        if "lb" in ids:
            if "frontend" in ids:
                _add("lb", "frontend")
            elif "api" in ids:
                _add("lb", "api")

        # frontend → api (for web_app)
        if spec.app_type == "web_app":
            _add("frontend", "api", weight=0.9)

        # api → database
        _add("api", "database")

        # api → cache (optional)
        _add("api", "cache", dep_type="optional", weight=0.5)

        # api → queue (optional)
        _add("api", "queue", dep_type="optional", weight=0.3)

        # api → search (optional)
        _add("api", "search", dep_type="optional", weight=0.3)

        # api → storage (optional)
        _add("api", "storage", dep_type="optional", weight=0.2)

        # queue → database (data pipeline)
        if spec.app_type == "data_pipeline":
            _add("queue", "database", weight=0.8)
            _add("queue", "storage", dep_type="optional", weight=0.5)
