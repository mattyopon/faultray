"""Infrastructure Template Gallery.

Pre-built, production-ready infrastructure templates optimized for resilience.
Each template represents a well-architected reference architecture with:
- Proper redundancy
- Failover configured
- Circuit breakers enabled
- Health checks set up
- Industry-appropriate compliance tags

Templates serve as:
1. Starting points for new projects
2. Reference architectures for comparison
3. Best-practice examples
4. Training material for teams learning resilience patterns
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import yaml

from faultray.model.components import (
    AutoScalingConfig,
    Capacity,
    CircuitBreakerConfig,
    ComplianceTags,
    Component,
    ComponentType,
    CostProfile,
    Dependency,
    FailoverConfig,
    ResourceMetrics,
    RetryStrategy,
    SecurityProfile,
)
from faultray.model.graph import InfraGraph

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enums and dataclasses
# ---------------------------------------------------------------------------


class TemplateCategory(str, Enum):
    """Category of infrastructure template."""

    WEB_APPLICATION = "web_application"
    MICROSERVICES = "microservices"
    DATA_PIPELINE = "data_pipeline"
    EVENT_DRIVEN = "event_driven"
    SERVERLESS = "serverless"
    MACHINE_LEARNING = "machine_learning"
    IOT = "iot"
    EDGE_COMPUTING = "edge_computing"
    AI_AGENTS = "ai_agents"


@dataclass
class InfraTemplate:
    """A pre-built infrastructure template."""

    id: str
    name: str
    category: TemplateCategory
    description: str
    architecture_style: str
    target_nines: float
    estimated_monthly_cost: str
    components: list[dict]
    edges: list[dict]
    resilience_score: float
    tags: list[str] = field(default_factory=list)
    difficulty: str = "intermediate"  # starter, intermediate, advanced, expert
    cloud_provider: str = "cloud-agnostic"
    compliance: list[str] = field(default_factory=list)
    diagram_mermaid: str = ""
    best_practices: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Built-in templates
# ---------------------------------------------------------------------------

GALLERY_TEMPLATES: list[InfraTemplate] = [
    InfraTemplate(
        id="ha-web-3tier",
        name="High-Availability 3-Tier Web Application",
        category=TemplateCategory.WEB_APPLICATION,
        description=(
            "Classic 3-tier web app with ALB, auto-scaled app servers, "
            "Aurora with read replicas, and Redis cache. Designed for 99.99% uptime."
        ),
        architecture_style="3-tier",
        target_nines=4.0,
        estimated_monthly_cost="$2,000-5,000",
        components=[
            {
                "id": "cdn",
                "name": "CloudFront CDN",
                "type": "dns",
                "replicas": 1,
                "capacity": {"max_connections": 100000, "max_rps": 200000},
                "metrics": {"cpu_percent": 5, "memory_percent": 10, "network_connections": 2000},
                "security": {"encryption_in_transit": True, "waf_protected": True, "rate_limiting": True, "log_enabled": True},
                "cost_profile": {"hourly_infra_cost": 0.10},
            },
            {
                "id": "alb",
                "name": "Application Load Balancer",
                "type": "load_balancer",
                "replicas": 2,
                "capacity": {"max_connections": 50000, "max_rps": 100000},
                "metrics": {"cpu_percent": 8, "memory_percent": 12, "network_connections": 1500},
                "failover": {"enabled": True, "promotion_time_seconds": 5},
                "security": {"encryption_in_transit": True, "waf_protected": True, "rate_limiting": True, "log_enabled": True},
                "cost_profile": {"hourly_infra_cost": 0.30},
            },
            {
                "id": "web",
                "name": "Web Servers",
                "type": "app_server",
                "replicas": 3,
                "capacity": {"max_connections": 5000, "max_rps": 15000, "timeout_seconds": 30},
                "metrics": {"cpu_percent": 35, "memory_percent": 45, "network_connections": 800},
                "autoscaling": {"enabled": True, "min_replicas": 2, "max_replicas": 10, "scale_up_threshold": 70},
                "security": {"encryption_in_transit": True, "auth_required": True, "log_enabled": True},
                "cost_profile": {"hourly_infra_cost": 0.60},
            },
            {
                "id": "db-primary",
                "name": "Aurora Primary",
                "type": "database",
                "replicas": 2,
                "capacity": {"max_connections": 1000, "max_disk_gb": 500, "max_memory_mb": 32768},
                "metrics": {"cpu_percent": 30, "memory_percent": 50, "disk_percent": 25, "network_connections": 200},
                "failover": {"enabled": True, "promotion_time_seconds": 30, "health_check_interval_seconds": 5},
                "security": {"encryption_at_rest": True, "encryption_in_transit": True, "backup_enabled": True, "backup_frequency_hours": 1, "network_segmented": True, "log_enabled": True},
                "cost_profile": {"hourly_infra_cost": 2.00},
                "compliance_tags": {"data_classification": "confidential", "contains_pii": True, "audit_logging": True},
            },
            {
                "id": "db-replica",
                "name": "Aurora Read Replica",
                "type": "database",
                "replicas": 2,
                "capacity": {"max_connections": 800, "max_disk_gb": 500, "max_memory_mb": 32768},
                "metrics": {"cpu_percent": 20, "memory_percent": 40, "disk_percent": 25, "network_connections": 150},
                "failover": {"enabled": True, "promotion_time_seconds": 15},
                "security": {"encryption_at_rest": True, "encryption_in_transit": True, "network_segmented": True, "log_enabled": True},
                "cost_profile": {"hourly_infra_cost": 1.50},
            },
            {
                "id": "cache",
                "name": "Redis Cache",
                "type": "cache",
                "replicas": 2,
                "capacity": {"max_connections": 20000, "max_memory_mb": 8192},
                "metrics": {"cpu_percent": 10, "memory_percent": 55, "network_connections": 500},
                "failover": {"enabled": True, "promotion_time_seconds": 5},
                "security": {"encryption_in_transit": True, "auth_required": True, "network_segmented": True},
                "cost_profile": {"hourly_infra_cost": 0.40},
            },
        ],
        edges=[
            {"source": "cdn", "target": "alb", "type": "requires", "protocol": "https", "latency_ms": 5.0, "circuit_breaker": {"enabled": True, "failure_threshold": 5}},
            {"source": "alb", "target": "web", "type": "requires", "protocol": "http", "latency_ms": 1.0, "circuit_breaker": {"enabled": True, "failure_threshold": 5}},
            {"source": "web", "target": "db-primary", "type": "requires", "protocol": "tcp", "latency_ms": 2.0, "circuit_breaker": {"enabled": True, "failure_threshold": 3}, "retry_strategy": {"enabled": True, "max_retries": 3}},
            {"source": "web", "target": "db-replica", "type": "optional", "protocol": "tcp", "latency_ms": 2.0, "weight": 0.8},
            {"source": "web", "target": "cache", "type": "optional", "protocol": "tcp", "latency_ms": 0.5, "weight": 0.7, "circuit_breaker": {"enabled": True, "failure_threshold": 5}},
        ],
        resilience_score=92.0,
        tags=["3-tier", "ha", "web", "aurora", "redis", "cdn"],
        difficulty="intermediate",
        cloud_provider="aws",
        compliance=["SOC2"],
        diagram_mermaid=(
            "graph TD\n"
            "    CDN[CloudFront CDN] --> ALB[Application Load Balancer]\n"
            "    ALB --> WEB[Web Servers x3]\n"
            "    WEB --> DB_P[Aurora Primary x2]\n"
            "    WEB -.-> DB_R[Aurora Read Replica x2]\n"
            "    WEB -.-> CACHE[Redis Cache x2]"
        ),
        best_practices=[
            "Multi-AZ deployment for all tiers",
            "Auto-scaling enabled for web servers",
            "Read replicas for read-heavy workloads",
            "Circuit breakers on all required dependencies",
            "CDN for static content acceleration",
        ],
    ),
    InfraTemplate(
        id="microservices-k8s",
        name="Microservices on Kubernetes",
        category=TemplateCategory.MICROSERVICES,
        description=(
            "Event-driven microservices with API Gateway, 5 services, "
            "Kafka event bus, PostgreSQL per service, and centralized monitoring."
        ),
        architecture_style="microservices",
        target_nines=3.5,
        estimated_monthly_cost="$5,000-12,000",
        components=[
            {
                "id": "gateway",
                "name": "API Gateway",
                "type": "load_balancer",
                "replicas": 2,
                "capacity": {"max_connections": 30000, "max_rps": 80000},
                "metrics": {"cpu_percent": 15, "memory_percent": 20, "network_connections": 3000},
                "failover": {"enabled": True, "promotion_time_seconds": 10},
                "security": {"encryption_in_transit": True, "waf_protected": True, "rate_limiting": True, "auth_required": True, "log_enabled": True},
                "cost_profile": {"hourly_infra_cost": 0.50},
            },
            {
                "id": "svc-users",
                "name": "User Service",
                "type": "app_server",
                "replicas": 3,
                "capacity": {"max_connections": 3000, "max_rps": 8000},
                "metrics": {"cpu_percent": 30, "memory_percent": 40, "network_connections": 400},
                "autoscaling": {"enabled": True, "min_replicas": 2, "max_replicas": 8},
                "security": {"encryption_in_transit": True, "auth_required": True, "log_enabled": True},
                "cost_profile": {"hourly_infra_cost": 0.40},
            },
            {
                "id": "svc-orders",
                "name": "Order Service",
                "type": "app_server",
                "replicas": 3,
                "capacity": {"max_connections": 3000, "max_rps": 8000},
                "metrics": {"cpu_percent": 35, "memory_percent": 50, "network_connections": 500},
                "autoscaling": {"enabled": True, "min_replicas": 2, "max_replicas": 10},
                "security": {"encryption_in_transit": True, "auth_required": True, "log_enabled": True},
                "cost_profile": {"hourly_infra_cost": 0.40},
            },
            {
                "id": "svc-payments",
                "name": "Payment Service",
                "type": "app_server",
                "replicas": 3,
                "capacity": {"max_connections": 2000, "max_rps": 5000},
                "metrics": {"cpu_percent": 25, "memory_percent": 35, "network_connections": 300},
                "autoscaling": {"enabled": True, "min_replicas": 2, "max_replicas": 6},
                "security": {"encryption_in_transit": True, "encryption_at_rest": True, "auth_required": True, "log_enabled": True},
                "cost_profile": {"hourly_infra_cost": 0.40},
            },
            {
                "id": "svc-notifications",
                "name": "Notification Service",
                "type": "app_server",
                "replicas": 2,
                "capacity": {"max_connections": 2000, "max_rps": 6000},
                "metrics": {"cpu_percent": 20, "memory_percent": 30, "network_connections": 200},
                "autoscaling": {"enabled": True, "min_replicas": 1, "max_replicas": 5},
                "security": {"encryption_in_transit": True, "log_enabled": True},
                "cost_profile": {"hourly_infra_cost": 0.30},
            },
            {
                "id": "kafka",
                "name": "Kafka Event Bus",
                "type": "queue",
                "replicas": 3,
                "capacity": {"max_connections": 10000, "max_rps": 100000},
                "metrics": {"cpu_percent": 40, "memory_percent": 60, "disk_percent": 30, "network_connections": 800},
                "failover": {"enabled": True, "promotion_time_seconds": 15},
                "security": {"encryption_in_transit": True, "auth_required": True, "log_enabled": True},
                "cost_profile": {"hourly_infra_cost": 1.00},
            },
            {
                "id": "db-users",
                "name": "User DB (PostgreSQL)",
                "type": "database",
                "replicas": 2,
                "capacity": {"max_connections": 300, "max_disk_gb": 100},
                "metrics": {"cpu_percent": 20, "memory_percent": 35, "disk_percent": 20, "network_connections": 80},
                "failover": {"enabled": True, "promotion_time_seconds": 30},
                "security": {"encryption_at_rest": True, "encryption_in_transit": True, "backup_enabled": True, "network_segmented": True, "log_enabled": True},
                "cost_profile": {"hourly_infra_cost": 0.80},
                "compliance_tags": {"data_classification": "confidential", "contains_pii": True, "audit_logging": True},
            },
            {
                "id": "db-orders",
                "name": "Order DB (PostgreSQL)",
                "type": "database",
                "replicas": 2,
                "capacity": {"max_connections": 300, "max_disk_gb": 200},
                "metrics": {"cpu_percent": 25, "memory_percent": 40, "disk_percent": 30, "network_connections": 100},
                "failover": {"enabled": True, "promotion_time_seconds": 30},
                "security": {"encryption_at_rest": True, "encryption_in_transit": True, "backup_enabled": True, "network_segmented": True, "log_enabled": True},
                "cost_profile": {"hourly_infra_cost": 0.80},
            },
        ],
        edges=[
            {"source": "gateway", "target": "svc-users", "type": "requires", "protocol": "grpc", "latency_ms": 2.0, "circuit_breaker": {"enabled": True, "failure_threshold": 5}},
            {"source": "gateway", "target": "svc-orders", "type": "requires", "protocol": "grpc", "latency_ms": 2.0, "circuit_breaker": {"enabled": True, "failure_threshold": 5}},
            {"source": "gateway", "target": "svc-payments", "type": "requires", "protocol": "grpc", "latency_ms": 3.0, "circuit_breaker": {"enabled": True, "failure_threshold": 3}},
            {"source": "svc-orders", "target": "kafka", "type": "requires", "protocol": "tcp", "latency_ms": 1.0, "circuit_breaker": {"enabled": True, "failure_threshold": 5}},
            {"source": "svc-payments", "target": "kafka", "type": "requires", "protocol": "tcp", "latency_ms": 1.0, "circuit_breaker": {"enabled": True, "failure_threshold": 3}},
            {"source": "kafka", "target": "svc-notifications", "type": "async", "protocol": "tcp", "latency_ms": 5.0},
            {"source": "svc-users", "target": "db-users", "type": "requires", "protocol": "tcp", "latency_ms": 2.0, "circuit_breaker": {"enabled": True, "failure_threshold": 3}, "retry_strategy": {"enabled": True, "max_retries": 3}},
            {"source": "svc-orders", "target": "db-orders", "type": "requires", "protocol": "tcp", "latency_ms": 2.0, "circuit_breaker": {"enabled": True, "failure_threshold": 3}, "retry_strategy": {"enabled": True, "max_retries": 3}},
        ],
        resilience_score=85.0,
        tags=["microservices", "kubernetes", "kafka", "grpc", "event-driven"],
        difficulty="advanced",
        cloud_provider="cloud-agnostic",
        compliance=["SOC2"],
        diagram_mermaid=(
            "graph TD\n"
            "    GW[API Gateway] --> USR[User Service x3]\n"
            "    GW --> ORD[Order Service x3]\n"
            "    GW --> PAY[Payment Service x3]\n"
            "    ORD --> KFK[Kafka x3]\n"
            "    PAY --> KFK\n"
            "    KFK -.-> NTF[Notification Service x2]\n"
            "    USR --> DB_U[User DB x2]\n"
            "    ORD --> DB_O[Order DB x2]"
        ),
        best_practices=[
            "Database per service pattern",
            "Event bus for asynchronous communication",
            "Circuit breakers on all synchronous calls",
            "Independent scaling per service",
            "Centralized logging and tracing",
        ],
    ),
    InfraTemplate(
        id="data-pipeline-streaming",
        name="Real-Time Data Pipeline",
        category=TemplateCategory.DATA_PIPELINE,
        description=(
            "Kafka-based streaming pipeline with producers, Spark processing, "
            "data lake storage, and analytics dashboard."
        ),
        architecture_style="streaming",
        target_nines=3.0,
        estimated_monthly_cost="$3,000-8,000",
        components=[
            {
                "id": "producers",
                "name": "Data Producers",
                "type": "app_server",
                "replicas": 4,
                "capacity": {"max_connections": 5000, "max_rps": 20000},
                "metrics": {"cpu_percent": 40, "memory_percent": 35, "network_connections": 1000},
                "autoscaling": {"enabled": True, "min_replicas": 2, "max_replicas": 10},
                "security": {"encryption_in_transit": True, "log_enabled": True},
                "cost_profile": {"hourly_infra_cost": 0.30},
            },
            {
                "id": "kafka-stream",
                "name": "Kafka Cluster",
                "type": "queue",
                "replicas": 3,
                "capacity": {"max_connections": 15000, "max_rps": 200000},
                "metrics": {"cpu_percent": 50, "memory_percent": 65, "disk_percent": 40, "network_connections": 2000},
                "failover": {"enabled": True, "promotion_time_seconds": 10},
                "security": {"encryption_in_transit": True, "encryption_at_rest": True, "auth_required": True, "log_enabled": True},
                "cost_profile": {"hourly_infra_cost": 1.50},
            },
            {
                "id": "spark",
                "name": "Spark Processing Cluster",
                "type": "app_server",
                "replicas": 3,
                "capacity": {"max_connections": 500, "max_memory_mb": 65536},
                "metrics": {"cpu_percent": 60, "memory_percent": 70, "network_connections": 200},
                "autoscaling": {"enabled": True, "min_replicas": 2, "max_replicas": 8},
                "security": {"encryption_in_transit": True, "log_enabled": True},
                "cost_profile": {"hourly_infra_cost": 2.00},
            },
            {
                "id": "datalake",
                "name": "Data Lake (S3/GCS)",
                "type": "storage",
                "replicas": 1,
                "capacity": {"max_disk_gb": 10000},
                "metrics": {"disk_percent": 15},
                "security": {"encryption_at_rest": True, "encryption_in_transit": True, "backup_enabled": True, "log_enabled": True},
                "cost_profile": {"hourly_infra_cost": 0.50},
            },
            {
                "id": "analytics-db",
                "name": "Analytics Database",
                "type": "database",
                "replicas": 2,
                "capacity": {"max_connections": 200, "max_disk_gb": 500},
                "metrics": {"cpu_percent": 35, "memory_percent": 50, "disk_percent": 30, "network_connections": 80},
                "failover": {"enabled": True, "promotion_time_seconds": 60},
                "security": {"encryption_at_rest": True, "encryption_in_transit": True, "backup_enabled": True, "network_segmented": True, "log_enabled": True},
                "cost_profile": {"hourly_infra_cost": 1.20},
            },
            {
                "id": "dashboard",
                "name": "Analytics Dashboard",
                "type": "web_server",
                "replicas": 2,
                "capacity": {"max_connections": 1000, "max_rps": 3000},
                "metrics": {"cpu_percent": 15, "memory_percent": 25, "network_connections": 100},
                "security": {"encryption_in_transit": True, "auth_required": True, "log_enabled": True},
                "cost_profile": {"hourly_infra_cost": 0.20},
            },
        ],
        edges=[
            {"source": "producers", "target": "kafka-stream", "type": "requires", "protocol": "tcp", "latency_ms": 2.0, "circuit_breaker": {"enabled": True, "failure_threshold": 5}},
            {"source": "kafka-stream", "target": "spark", "type": "requires", "protocol": "tcp", "latency_ms": 5.0, "circuit_breaker": {"enabled": True, "failure_threshold": 3}},
            {"source": "spark", "target": "datalake", "type": "requires", "protocol": "https", "latency_ms": 10.0, "retry_strategy": {"enabled": True, "max_retries": 5}},
            {"source": "spark", "target": "analytics-db", "type": "requires", "protocol": "tcp", "latency_ms": 3.0, "circuit_breaker": {"enabled": True, "failure_threshold": 3}},
            {"source": "dashboard", "target": "analytics-db", "type": "requires", "protocol": "tcp", "latency_ms": 2.0, "circuit_breaker": {"enabled": True, "failure_threshold": 5}},
        ],
        resilience_score=78.0,
        tags=["data-pipeline", "kafka", "spark", "streaming", "analytics"],
        difficulty="advanced",
        cloud_provider="cloud-agnostic",
        diagram_mermaid=(
            "graph LR\n"
            "    PROD[Data Producers x4] --> KFK[Kafka Cluster x3]\n"
            "    KFK --> SPK[Spark Processing x3]\n"
            "    SPK --> DL[Data Lake]\n"
            "    SPK --> ADB[Analytics DB x2]\n"
            "    DASH[Dashboard x2] --> ADB"
        ),
        best_practices=[
            "Kafka replication factor >= 3",
            "Spark checkpointing for exactly-once semantics",
            "Data lake for raw data retention",
            "Analytics DB for fast queries",
            "Auto-scaling for producers and processors",
        ],
    ),
    InfraTemplate(
        id="serverless-api",
        name="Serverless API Backend",
        category=TemplateCategory.SERVERLESS,
        description=(
            "API Gateway + Lambda + DynamoDB + S3, designed for cost efficiency "
            "and auto-scaling. Pay per request with near-zero idle cost."
        ),
        architecture_style="serverless",
        target_nines=3.5,
        estimated_monthly_cost="$100-2,000",
        components=[
            {
                "id": "apigw",
                "name": "API Gateway",
                "type": "load_balancer",
                "replicas": 1,
                "capacity": {"max_connections": 100000, "max_rps": 50000},
                "metrics": {"cpu_percent": 5, "network_connections": 500},
                "security": {"encryption_in_transit": True, "waf_protected": True, "rate_limiting": True, "auth_required": True, "log_enabled": True},
                "cost_profile": {"hourly_infra_cost": 0.05},
            },
            {
                "id": "lambda-api",
                "name": "Lambda Functions (API)",
                "type": "app_server",
                "replicas": 1,
                "capacity": {"max_connections": 10000, "max_rps": 30000, "timeout_seconds": 30},
                "metrics": {"cpu_percent": 20, "memory_percent": 30},
                "autoscaling": {"enabled": True, "min_replicas": 1, "max_replicas": 1000},
                "security": {"encryption_in_transit": True, "log_enabled": True},
                "cost_profile": {"hourly_infra_cost": 0.10},
            },
            {
                "id": "dynamodb",
                "name": "DynamoDB",
                "type": "database",
                "replicas": 1,
                "capacity": {"max_connections": 50000, "max_rps": 40000},
                "metrics": {"cpu_percent": 10, "network_connections": 200},
                "autoscaling": {"enabled": True, "min_replicas": 1, "max_replicas": 1},
                "security": {"encryption_at_rest": True, "encryption_in_transit": True, "backup_enabled": True, "log_enabled": True},
                "cost_profile": {"hourly_infra_cost": 0.20},
                "compliance_tags": {"data_classification": "confidential", "audit_logging": True},
            },
            {
                "id": "s3-storage",
                "name": "S3 Object Storage",
                "type": "storage",
                "replicas": 1,
                "capacity": {"max_disk_gb": 5000},
                "metrics": {"disk_percent": 5},
                "security": {"encryption_at_rest": True, "encryption_in_transit": True, "backup_enabled": True, "log_enabled": True},
                "cost_profile": {"hourly_infra_cost": 0.05},
            },
            {
                "id": "cognito",
                "name": "Cognito Auth",
                "type": "external_api",
                "replicas": 1,
                "capacity": {"max_connections": 50000, "max_rps": 20000},
                "security": {"encryption_in_transit": True, "auth_required": True, "log_enabled": True},
                "cost_profile": {"hourly_infra_cost": 0.02},
            },
        ],
        edges=[
            {"source": "apigw", "target": "lambda-api", "type": "requires", "protocol": "https", "latency_ms": 5.0, "circuit_breaker": {"enabled": True, "failure_threshold": 5}},
            {"source": "apigw", "target": "cognito", "type": "requires", "protocol": "https", "latency_ms": 10.0},
            {"source": "lambda-api", "target": "dynamodb", "type": "requires", "protocol": "https", "latency_ms": 3.0, "retry_strategy": {"enabled": True, "max_retries": 3}},
            {"source": "lambda-api", "target": "s3-storage", "type": "optional", "protocol": "https", "latency_ms": 10.0, "weight": 0.5},
        ],
        resilience_score=80.0,
        tags=["serverless", "lambda", "dynamodb", "s3", "api-gateway"],
        difficulty="starter",
        cloud_provider="aws",
        compliance=["SOC2"],
        diagram_mermaid=(
            "graph TD\n"
            "    APIGW[API Gateway] --> AUTH[Cognito Auth]\n"
            "    APIGW --> FN[Lambda Functions]\n"
            "    FN --> DDB[DynamoDB]\n"
            "    FN -.-> S3[S3 Storage]"
        ),
        best_practices=[
            "Use provisioned concurrency for latency-sensitive endpoints",
            "DynamoDB on-demand for unpredictable workloads",
            "S3 lifecycle policies for cost optimization",
            "API Gateway throttling and WAF for security",
        ],
    ),
    InfraTemplate(
        id="ml-training-inference",
        name="ML Training & Inference Platform",
        category=TemplateCategory.MACHINE_LEARNING,
        description=(
            "GPU cluster for training, model registry, inference endpoint "
            "with autoscaling, and feature store."
        ),
        architecture_style="ml-platform",
        target_nines=3.0,
        estimated_monthly_cost="$8,000-25,000",
        components=[
            {
                "id": "training-cluster",
                "name": "GPU Training Cluster",
                "type": "app_server",
                "replicas": 2,
                "capacity": {"max_connections": 100, "max_memory_mb": 131072},
                "metrics": {"cpu_percent": 80, "memory_percent": 70, "network_connections": 20},
                "autoscaling": {"enabled": True, "min_replicas": 1, "max_replicas": 8},
                "security": {"encryption_in_transit": True, "log_enabled": True},
                "cost_profile": {"hourly_infra_cost": 5.00},
            },
            {
                "id": "model-registry",
                "name": "Model Registry",
                "type": "storage",
                "replicas": 1,
                "capacity": {"max_disk_gb": 2000},
                "metrics": {"disk_percent": 25},
                "security": {"encryption_at_rest": True, "encryption_in_transit": True, "backup_enabled": True, "log_enabled": True},
                "cost_profile": {"hourly_infra_cost": 0.20},
            },
            {
                "id": "inference-endpoint",
                "name": "Inference Endpoint",
                "type": "app_server",
                "replicas": 3,
                "capacity": {"max_connections": 5000, "max_rps": 10000, "timeout_seconds": 10},
                "metrics": {"cpu_percent": 50, "memory_percent": 60, "network_connections": 800},
                "autoscaling": {"enabled": True, "min_replicas": 2, "max_replicas": 20},
                "security": {"encryption_in_transit": True, "auth_required": True, "rate_limiting": True, "log_enabled": True},
                "cost_profile": {"hourly_infra_cost": 2.00},
            },
            {
                "id": "feature-store",
                "name": "Feature Store",
                "type": "database",
                "replicas": 2,
                "capacity": {"max_connections": 500, "max_disk_gb": 500},
                "metrics": {"cpu_percent": 30, "memory_percent": 45, "disk_percent": 20, "network_connections": 100},
                "failover": {"enabled": True, "promotion_time_seconds": 30},
                "security": {"encryption_at_rest": True, "encryption_in_transit": True, "backup_enabled": True, "log_enabled": True},
                "cost_profile": {"hourly_infra_cost": 1.00},
            },
            {
                "id": "ml-lb",
                "name": "ML Load Balancer",
                "type": "load_balancer",
                "replicas": 2,
                "capacity": {"max_connections": 20000, "max_rps": 50000},
                "metrics": {"cpu_percent": 10, "memory_percent": 15, "network_connections": 500},
                "failover": {"enabled": True, "promotion_time_seconds": 5},
                "security": {"encryption_in_transit": True, "rate_limiting": True, "log_enabled": True},
                "cost_profile": {"hourly_infra_cost": 0.25},
            },
        ],
        edges=[
            {"source": "ml-lb", "target": "inference-endpoint", "type": "requires", "protocol": "http", "latency_ms": 1.0, "circuit_breaker": {"enabled": True, "failure_threshold": 5}},
            {"source": "training-cluster", "target": "feature-store", "type": "requires", "protocol": "tcp", "latency_ms": 5.0, "circuit_breaker": {"enabled": True, "failure_threshold": 3}},
            {"source": "training-cluster", "target": "model-registry", "type": "requires", "protocol": "https", "latency_ms": 10.0, "retry_strategy": {"enabled": True, "max_retries": 3}},
            {"source": "inference-endpoint", "target": "model-registry", "type": "requires", "protocol": "https", "latency_ms": 5.0, "retry_strategy": {"enabled": True, "max_retries": 2}},
            {"source": "inference-endpoint", "target": "feature-store", "type": "optional", "protocol": "tcp", "latency_ms": 3.0, "weight": 0.6},
        ],
        resilience_score=75.0,
        tags=["ml", "gpu", "inference", "training", "feature-store"],
        difficulty="expert",
        cloud_provider="cloud-agnostic",
        diagram_mermaid=(
            "graph TD\n"
            "    LB[ML Load Balancer] --> INF[Inference Endpoint x3]\n"
            "    TRAIN[GPU Training x2] --> FS[Feature Store x2]\n"
            "    TRAIN --> MR[Model Registry]\n"
            "    INF --> MR\n"
            "    INF -.-> FS"
        ),
        best_practices=[
            "Separate training and inference clusters",
            "Model versioning in registry",
            "A/B testing for model deployments",
            "Feature store for consistent features",
            "GPU auto-scaling based on queue depth",
        ],
    ),
    InfraTemplate(
        id="multi-region-active-active",
        name="Multi-Region Active-Active",
        category=TemplateCategory.WEB_APPLICATION,
        description=(
            "Active-active deployment across 2 regions with global load balancing, "
            "replicated databases, and DNS failover. Maximum availability."
        ),
        architecture_style="multi-region active-active",
        target_nines=4.5,
        estimated_monthly_cost="$10,000-25,000",
        components=[
            {
                "id": "global-lb",
                "name": "Global Load Balancer / DNS",
                "type": "dns",
                "replicas": 1,
                "capacity": {"max_connections": 200000, "max_rps": 500000},
                "metrics": {"cpu_percent": 3, "network_connections": 5000},
                "security": {"encryption_in_transit": True, "waf_protected": True, "log_enabled": True},
                "cost_profile": {"hourly_infra_cost": 0.50},
            },
            {
                "id": "region1-lb",
                "name": "Region 1 ALB",
                "type": "load_balancer",
                "replicas": 2,
                "capacity": {"max_connections": 50000, "max_rps": 100000},
                "metrics": {"cpu_percent": 10, "memory_percent": 15, "network_connections": 2000},
                "failover": {"enabled": True, "promotion_time_seconds": 5},
                "security": {"encryption_in_transit": True, "waf_protected": True, "log_enabled": True},
                "cost_profile": {"hourly_infra_cost": 0.30},
            },
            {
                "id": "region2-lb",
                "name": "Region 2 ALB",
                "type": "load_balancer",
                "replicas": 2,
                "capacity": {"max_connections": 50000, "max_rps": 100000},
                "metrics": {"cpu_percent": 10, "memory_percent": 15, "network_connections": 2000},
                "failover": {"enabled": True, "promotion_time_seconds": 5},
                "security": {"encryption_in_transit": True, "waf_protected": True, "log_enabled": True},
                "cost_profile": {"hourly_infra_cost": 0.30},
            },
            {
                "id": "region1-app",
                "name": "Region 1 App Servers",
                "type": "app_server",
                "replicas": 3,
                "capacity": {"max_connections": 5000, "max_rps": 15000},
                "metrics": {"cpu_percent": 30, "memory_percent": 40, "network_connections": 600},
                "autoscaling": {"enabled": True, "min_replicas": 2, "max_replicas": 10},
                "security": {"encryption_in_transit": True, "auth_required": True, "log_enabled": True},
                "cost_profile": {"hourly_infra_cost": 0.60},
            },
            {
                "id": "region2-app",
                "name": "Region 2 App Servers",
                "type": "app_server",
                "replicas": 3,
                "capacity": {"max_connections": 5000, "max_rps": 15000},
                "metrics": {"cpu_percent": 30, "memory_percent": 40, "network_connections": 600},
                "autoscaling": {"enabled": True, "min_replicas": 2, "max_replicas": 10},
                "security": {"encryption_in_transit": True, "auth_required": True, "log_enabled": True},
                "cost_profile": {"hourly_infra_cost": 0.60},
            },
            {
                "id": "region1-db",
                "name": "Region 1 Database",
                "type": "database",
                "replicas": 2,
                "capacity": {"max_connections": 1000, "max_disk_gb": 500},
                "metrics": {"cpu_percent": 25, "memory_percent": 45, "disk_percent": 20, "network_connections": 150},
                "failover": {"enabled": True, "promotion_time_seconds": 30},
                "security": {"encryption_at_rest": True, "encryption_in_transit": True, "backup_enabled": True, "backup_frequency_hours": 1, "network_segmented": True, "log_enabled": True},
                "cost_profile": {"hourly_infra_cost": 2.00},
                "compliance_tags": {"data_classification": "confidential", "contains_pii": True, "audit_logging": True},
            },
            {
                "id": "region2-db",
                "name": "Region 2 Database",
                "type": "database",
                "replicas": 2,
                "capacity": {"max_connections": 1000, "max_disk_gb": 500},
                "metrics": {"cpu_percent": 25, "memory_percent": 45, "disk_percent": 20, "network_connections": 150},
                "failover": {"enabled": True, "promotion_time_seconds": 30},
                "security": {"encryption_at_rest": True, "encryption_in_transit": True, "backup_enabled": True, "backup_frequency_hours": 1, "network_segmented": True, "log_enabled": True},
                "cost_profile": {"hourly_infra_cost": 2.00},
                "compliance_tags": {"data_classification": "confidential", "contains_pii": True, "audit_logging": True},
            },
        ],
        edges=[
            {"source": "global-lb", "target": "region1-lb", "type": "requires", "protocol": "https", "latency_ms": 1.0},
            {"source": "global-lb", "target": "region2-lb", "type": "requires", "protocol": "https", "latency_ms": 1.0},
            {"source": "region1-lb", "target": "region1-app", "type": "requires", "protocol": "http", "latency_ms": 1.0, "circuit_breaker": {"enabled": True, "failure_threshold": 5}},
            {"source": "region2-lb", "target": "region2-app", "type": "requires", "protocol": "http", "latency_ms": 1.0, "circuit_breaker": {"enabled": True, "failure_threshold": 5}},
            {"source": "region1-app", "target": "region1-db", "type": "requires", "protocol": "tcp", "latency_ms": 2.0, "circuit_breaker": {"enabled": True, "failure_threshold": 3}, "retry_strategy": {"enabled": True, "max_retries": 3}},
            {"source": "region2-app", "target": "region2-db", "type": "requires", "protocol": "tcp", "latency_ms": 2.0, "circuit_breaker": {"enabled": True, "failure_threshold": 3}, "retry_strategy": {"enabled": True, "max_retries": 3}},
        ],
        resilience_score=95.0,
        tags=["multi-region", "active-active", "ha", "dns-failover", "global"],
        difficulty="expert",
        cloud_provider="aws",
        compliance=["SOC2", "ISO27001"],
        diagram_mermaid=(
            "graph TD\n"
            "    GLB[Global LB / DNS] --> R1LB[Region 1 ALB]\n"
            "    GLB --> R2LB[Region 2 ALB]\n"
            "    R1LB --> R1APP[Region 1 App x3]\n"
            "    R2LB --> R2APP[Region 2 App x3]\n"
            "    R1APP --> R1DB[Region 1 DB x2]\n"
            "    R2APP --> R2DB[Region 2 DB x2]"
        ),
        best_practices=[
            "Global load balancer with health-based routing",
            "Cross-region database replication",
            "Eventual consistency model between regions",
            "Automated DNS failover on region outage",
            "Regular cross-region failover testing",
        ],
    ),
    InfraTemplate(
        id="iot-edge",
        name="IoT Edge Computing Platform",
        category=TemplateCategory.IOT,
        description=(
            "Edge gateways collecting sensor data, MQTT broker, "
            "time-series DB, and analytics pipeline."
        ),
        architecture_style="edge-cloud hybrid",
        target_nines=3.0,
        estimated_monthly_cost="$2,000-6,000",
        components=[
            {
                "id": "edge-gw",
                "name": "Edge Gateways",
                "type": "app_server",
                "replicas": 4,
                "capacity": {"max_connections": 10000, "max_rps": 20000},
                "metrics": {"cpu_percent": 30, "memory_percent": 35, "network_connections": 2000},
                "autoscaling": {"enabled": True, "min_replicas": 2, "max_replicas": 20},
                "security": {"encryption_in_transit": True, "auth_required": True, "log_enabled": True},
                "cost_profile": {"hourly_infra_cost": 0.20},
            },
            {
                "id": "mqtt",
                "name": "MQTT Broker",
                "type": "queue",
                "replicas": 3,
                "capacity": {"max_connections": 50000, "max_rps": 100000},
                "metrics": {"cpu_percent": 35, "memory_percent": 45, "network_connections": 5000},
                "failover": {"enabled": True, "promotion_time_seconds": 10},
                "security": {"encryption_in_transit": True, "auth_required": True, "log_enabled": True},
                "cost_profile": {"hourly_infra_cost": 0.60},
            },
            {
                "id": "timeseries-db",
                "name": "TimescaleDB",
                "type": "database",
                "replicas": 2,
                "capacity": {"max_connections": 500, "max_disk_gb": 1000},
                "metrics": {"cpu_percent": 40, "memory_percent": 55, "disk_percent": 35, "network_connections": 100},
                "failover": {"enabled": True, "promotion_time_seconds": 30},
                "security": {"encryption_at_rest": True, "encryption_in_transit": True, "backup_enabled": True, "network_segmented": True, "log_enabled": True},
                "cost_profile": {"hourly_infra_cost": 1.00},
            },
            {
                "id": "iot-analytics",
                "name": "Analytics Engine",
                "type": "app_server",
                "replicas": 2,
                "capacity": {"max_connections": 500, "max_rps": 5000},
                "metrics": {"cpu_percent": 50, "memory_percent": 60, "network_connections": 80},
                "security": {"encryption_in_transit": True, "log_enabled": True},
                "cost_profile": {"hourly_infra_cost": 0.50},
            },
            {
                "id": "iot-dashboard",
                "name": "IoT Dashboard",
                "type": "web_server",
                "replicas": 2,
                "capacity": {"max_connections": 2000, "max_rps": 5000},
                "metrics": {"cpu_percent": 15, "memory_percent": 20, "network_connections": 200},
                "security": {"encryption_in_transit": True, "auth_required": True, "log_enabled": True},
                "cost_profile": {"hourly_infra_cost": 0.15},
            },
        ],
        edges=[
            {"source": "edge-gw", "target": "mqtt", "type": "requires", "protocol": "mqtt", "latency_ms": 10.0, "circuit_breaker": {"enabled": True, "failure_threshold": 5}},
            {"source": "mqtt", "target": "timeseries-db", "type": "requires", "protocol": "tcp", "latency_ms": 3.0, "circuit_breaker": {"enabled": True, "failure_threshold": 3}},
            {"source": "mqtt", "target": "iot-analytics", "type": "async", "protocol": "tcp", "latency_ms": 5.0},
            {"source": "iot-analytics", "target": "timeseries-db", "type": "requires", "protocol": "tcp", "latency_ms": 3.0, "circuit_breaker": {"enabled": True, "failure_threshold": 3}},
            {"source": "iot-dashboard", "target": "timeseries-db", "type": "requires", "protocol": "tcp", "latency_ms": 2.0},
        ],
        resilience_score=76.0,
        tags=["iot", "edge", "mqtt", "timeseries", "sensors"],
        difficulty="advanced",
        cloud_provider="cloud-agnostic",
        diagram_mermaid=(
            "graph TD\n"
            "    EDGE[Edge Gateways x4] --> MQTT[MQTT Broker x3]\n"
            "    MQTT --> TSDB[TimescaleDB x2]\n"
            "    MQTT -.-> ANA[Analytics Engine x2]\n"
            "    ANA --> TSDB\n"
            "    DASH[IoT Dashboard x2] --> TSDB"
        ),
        best_practices=[
            "Edge-local buffering for connectivity failures",
            "MQTT QoS levels matched to data criticality",
            "Time-series data partitioning and retention policies",
            "Asynchronous analytics processing",
        ],
    ),
    InfraTemplate(
        id="ecommerce-peak",
        name="E-Commerce Peak Traffic Ready",
        category=TemplateCategory.WEB_APPLICATION,
        description=(
            "Designed for Black Friday scale: CDN, aggressive caching, "
            "queue-based order processing, and read replicas."
        ),
        architecture_style="event-driven with caching",
        target_nines=4.0,
        estimated_monthly_cost="$5,000-15,000",
        components=[
            {
                "id": "cdn-ec",
                "name": "CDN Edge",
                "type": "dns",
                "replicas": 1,
                "capacity": {"max_connections": 500000, "max_rps": 1000000},
                "metrics": {"cpu_percent": 3, "network_connections": 10000},
                "security": {"encryption_in_transit": True, "waf_protected": True, "rate_limiting": True, "log_enabled": True},
                "cost_profile": {"hourly_infra_cost": 0.50},
            },
            {
                "id": "ec-lb",
                "name": "E-Commerce Load Balancer",
                "type": "load_balancer",
                "replicas": 2,
                "capacity": {"max_connections": 100000, "max_rps": 200000},
                "metrics": {"cpu_percent": 10, "memory_percent": 15, "network_connections": 3000},
                "failover": {"enabled": True, "promotion_time_seconds": 5},
                "security": {"encryption_in_transit": True, "log_enabled": True},
                "cost_profile": {"hourly_infra_cost": 0.40},
            },
            {
                "id": "ec-app",
                "name": "Web Application",
                "type": "app_server",
                "replicas": 5,
                "capacity": {"max_connections": 5000, "max_rps": 20000},
                "metrics": {"cpu_percent": 40, "memory_percent": 50, "network_connections": 1500},
                "autoscaling": {"enabled": True, "min_replicas": 3, "max_replicas": 20, "scale_up_threshold": 60},
                "security": {"encryption_in_transit": True, "auth_required": True, "log_enabled": True},
                "cost_profile": {"hourly_infra_cost": 0.60},
            },
            {
                "id": "ec-cache",
                "name": "Redis Cache Cluster",
                "type": "cache",
                "replicas": 3,
                "capacity": {"max_connections": 30000, "max_memory_mb": 16384},
                "metrics": {"cpu_percent": 15, "memory_percent": 60, "network_connections": 1000},
                "failover": {"enabled": True, "promotion_time_seconds": 5},
                "security": {"encryption_in_transit": True, "auth_required": True, "network_segmented": True},
                "cost_profile": {"hourly_infra_cost": 0.80},
            },
            {
                "id": "ec-db-write",
                "name": "Primary DB (Write)",
                "type": "database",
                "replicas": 2,
                "capacity": {"max_connections": 1000, "max_disk_gb": 500},
                "metrics": {"cpu_percent": 35, "memory_percent": 50, "disk_percent": 25, "network_connections": 200},
                "failover": {"enabled": True, "promotion_time_seconds": 30},
                "security": {"encryption_at_rest": True, "encryption_in_transit": True, "backup_enabled": True, "backup_frequency_hours": 1, "network_segmented": True, "log_enabled": True},
                "cost_profile": {"hourly_infra_cost": 2.00},
                "compliance_tags": {"data_classification": "confidential", "contains_pii": True, "audit_logging": True},
            },
            {
                "id": "ec-db-read",
                "name": "Read Replicas",
                "type": "database",
                "replicas": 3,
                "capacity": {"max_connections": 800, "max_disk_gb": 500},
                "metrics": {"cpu_percent": 25, "memory_percent": 40, "disk_percent": 25, "network_connections": 150},
                "security": {"encryption_at_rest": True, "encryption_in_transit": True, "network_segmented": True, "log_enabled": True},
                "cost_profile": {"hourly_infra_cost": 1.50},
            },
            {
                "id": "ec-queue",
                "name": "Order Queue (SQS/RabbitMQ)",
                "type": "queue",
                "replicas": 2,
                "capacity": {"max_connections": 50000, "max_rps": 100000},
                "metrics": {"cpu_percent": 20, "memory_percent": 30, "network_connections": 300},
                "failover": {"enabled": True, "promotion_time_seconds": 10},
                "security": {"encryption_in_transit": True, "log_enabled": True},
                "cost_profile": {"hourly_infra_cost": 0.30},
            },
            {
                "id": "ec-worker",
                "name": "Order Workers",
                "type": "app_server",
                "replicas": 3,
                "capacity": {"max_connections": 1000, "max_rps": 5000},
                "metrics": {"cpu_percent": 45, "memory_percent": 40, "network_connections": 200},
                "autoscaling": {"enabled": True, "min_replicas": 2, "max_replicas": 15},
                "security": {"encryption_in_transit": True, "log_enabled": True},
                "cost_profile": {"hourly_infra_cost": 0.40},
            },
        ],
        edges=[
            {"source": "cdn-ec", "target": "ec-lb", "type": "requires", "protocol": "https", "latency_ms": 2.0},
            {"source": "ec-lb", "target": "ec-app", "type": "requires", "protocol": "http", "latency_ms": 1.0, "circuit_breaker": {"enabled": True, "failure_threshold": 5}},
            {"source": "ec-app", "target": "ec-cache", "type": "optional", "protocol": "tcp", "latency_ms": 0.5, "weight": 0.8, "circuit_breaker": {"enabled": True, "failure_threshold": 5}},
            {"source": "ec-app", "target": "ec-db-read", "type": "requires", "protocol": "tcp", "latency_ms": 2.0, "circuit_breaker": {"enabled": True, "failure_threshold": 3}},
            {"source": "ec-app", "target": "ec-queue", "type": "requires", "protocol": "tcp", "latency_ms": 1.0, "circuit_breaker": {"enabled": True, "failure_threshold": 5}},
            {"source": "ec-worker", "target": "ec-queue", "type": "requires", "protocol": "tcp", "latency_ms": 1.0},
            {"source": "ec-worker", "target": "ec-db-write", "type": "requires", "protocol": "tcp", "latency_ms": 2.0, "circuit_breaker": {"enabled": True, "failure_threshold": 3}, "retry_strategy": {"enabled": True, "max_retries": 3}},
        ],
        resilience_score=88.0,
        tags=["ecommerce", "peak-traffic", "caching", "queue", "read-replicas"],
        difficulty="advanced",
        cloud_provider="aws",
        compliance=["PCI_DSS", "SOC2"],
        diagram_mermaid=(
            "graph TD\n"
            "    CDN[CDN Edge] --> LB[Load Balancer]\n"
            "    LB --> APP[Web App x5]\n"
            "    APP -.-> CACHE[Redis Cache x3]\n"
            "    APP --> DBR[Read Replicas x3]\n"
            "    APP --> Q[Order Queue x2]\n"
            "    WRK[Order Workers x3] --> Q\n"
            "    WRK --> DBW[Primary DB x2]"
        ),
        best_practices=[
            "Queue-based order processing for peak absorbing",
            "Read replicas for catalog reads",
            "Aggressive caching for product pages",
            "CDN for static assets",
            "Auto-scaling with pre-warm before sales events",
        ],
    ),
    InfraTemplate(
        id="healthcare-hipaa",
        name="HIPAA-Compliant Healthcare Platform",
        category=TemplateCategory.WEB_APPLICATION,
        description=(
            "Encrypted at rest/transit, audit logging, VPN access, "
            "HIPAA compliance tags throughout."
        ),
        architecture_style="secure 3-tier",
        target_nines=4.0,
        estimated_monthly_cost="$5,000-12,000",
        components=[
            {
                "id": "vpn-gw",
                "name": "VPN Gateway",
                "type": "load_balancer",
                "replicas": 2,
                "capacity": {"max_connections": 10000, "max_rps": 20000},
                "metrics": {"cpu_percent": 15, "memory_percent": 20, "network_connections": 500},
                "failover": {"enabled": True, "promotion_time_seconds": 15},
                "security": {"encryption_in_transit": True, "auth_required": True, "network_segmented": True, "log_enabled": True},
                "cost_profile": {"hourly_infra_cost": 0.50},
            },
            {
                "id": "health-app",
                "name": "Healthcare Application",
                "type": "app_server",
                "replicas": 3,
                "capacity": {"max_connections": 3000, "max_rps": 8000},
                "metrics": {"cpu_percent": 30, "memory_percent": 40, "network_connections": 400},
                "autoscaling": {"enabled": True, "min_replicas": 2, "max_replicas": 6},
                "security": {"encryption_in_transit": True, "auth_required": True, "log_enabled": True, "ids_monitored": True},
                "cost_profile": {"hourly_infra_cost": 0.60},
            },
            {
                "id": "health-db",
                "name": "Patient Database",
                "type": "database",
                "replicas": 2,
                "capacity": {"max_connections": 500, "max_disk_gb": 300},
                "metrics": {"cpu_percent": 25, "memory_percent": 45, "disk_percent": 20, "network_connections": 100},
                "failover": {"enabled": True, "promotion_time_seconds": 30, "health_check_interval_seconds": 5},
                "security": {"encryption_at_rest": True, "encryption_in_transit": True, "backup_enabled": True, "backup_frequency_hours": 1, "network_segmented": True, "log_enabled": True, "ids_monitored": True},
                "cost_profile": {"hourly_infra_cost": 1.50},
                "compliance_tags": {"data_classification": "restricted", "contains_pii": True, "contains_phi": True, "audit_logging": True, "change_management": True},
            },
            {
                "id": "audit-log",
                "name": "Audit Log Store",
                "type": "storage",
                "replicas": 2,
                "capacity": {"max_disk_gb": 500},
                "metrics": {"disk_percent": 15},
                "failover": {"enabled": True, "promotion_time_seconds": 10},
                "security": {"encryption_at_rest": True, "encryption_in_transit": True, "backup_enabled": True, "log_enabled": True},
                "cost_profile": {"hourly_infra_cost": 0.30},
                "compliance_tags": {"data_classification": "restricted", "audit_logging": True},
            },
            {
                "id": "health-cache",
                "name": "Session Cache",
                "type": "cache",
                "replicas": 2,
                "capacity": {"max_connections": 5000, "max_memory_mb": 4096},
                "metrics": {"cpu_percent": 10, "memory_percent": 40, "network_connections": 200},
                "failover": {"enabled": True, "promotion_time_seconds": 5},
                "security": {"encryption_in_transit": True, "encryption_at_rest": True, "auth_required": True, "network_segmented": True},
                "cost_profile": {"hourly_infra_cost": 0.40},
            },
        ],
        edges=[
            {"source": "vpn-gw", "target": "health-app", "type": "requires", "protocol": "https", "latency_ms": 5.0, "circuit_breaker": {"enabled": True, "failure_threshold": 3}},
            {"source": "health-app", "target": "health-db", "type": "requires", "protocol": "tcp", "latency_ms": 2.0, "circuit_breaker": {"enabled": True, "failure_threshold": 3}, "retry_strategy": {"enabled": True, "max_retries": 3}},
            {"source": "health-app", "target": "audit-log", "type": "requires", "protocol": "tcp", "latency_ms": 1.0, "circuit_breaker": {"enabled": True, "failure_threshold": 5}},
            {"source": "health-app", "target": "health-cache", "type": "optional", "protocol": "tcp", "latency_ms": 0.5, "weight": 0.7, "circuit_breaker": {"enabled": True, "failure_threshold": 5}},
        ],
        resilience_score=90.0,
        tags=["healthcare", "hipaa", "encrypted", "audit-logging", "phi"],
        difficulty="advanced",
        cloud_provider="aws",
        compliance=["HIPAA", "SOC2"],
        diagram_mermaid=(
            "graph TD\n"
            "    VPN[VPN Gateway x2] --> APP[Healthcare App x3]\n"
            "    APP --> DB[Patient DB x2]\n"
            "    APP --> AUDIT[Audit Log Store x2]\n"
            "    APP -.-> CACHE[Session Cache x2]"
        ),
        best_practices=[
            "All data encrypted at rest and in transit",
            "Comprehensive audit logging with tamper-proof storage",
            "VPN-only access for healthcare workers",
            "PHI data classification on all relevant components",
            "Regular compliance audits and penetration testing",
        ],
    ),
    InfraTemplate(
        id="fintech-dora",
        name="DORA-Compliant Financial Platform",
        category=TemplateCategory.WEB_APPLICATION,
        description=(
            "Banking-grade infrastructure meeting all DORA requirements "
            "with third-party risk isolation and mandatory ICT testing."
        ),
        architecture_style="secure multi-tier",
        target_nines=4.5,
        estimated_monthly_cost="$15,000-35,000",
        components=[
            {
                "id": "waf-fin",
                "name": "WAF / DDoS Protection",
                "type": "load_balancer",
                "replicas": 2,
                "capacity": {"max_connections": 100000, "max_rps": 200000},
                "metrics": {"cpu_percent": 10, "memory_percent": 15, "network_connections": 2000},
                "failover": {"enabled": True, "promotion_time_seconds": 5},
                "security": {"encryption_in_transit": True, "waf_protected": True, "rate_limiting": True, "ids_monitored": True, "log_enabled": True},
                "cost_profile": {"hourly_infra_cost": 1.00},
            },
            {
                "id": "fin-app",
                "name": "Banking Application",
                "type": "app_server",
                "replicas": 4,
                "capacity": {"max_connections": 5000, "max_rps": 15000},
                "metrics": {"cpu_percent": 35, "memory_percent": 45, "network_connections": 800},
                "autoscaling": {"enabled": True, "min_replicas": 3, "max_replicas": 10},
                "security": {"encryption_in_transit": True, "auth_required": True, "log_enabled": True, "ids_monitored": True},
                "cost_profile": {"hourly_infra_cost": 0.80},
            },
            {
                "id": "fin-db",
                "name": "Financial Database",
                "type": "database",
                "replicas": 3,
                "capacity": {"max_connections": 1000, "max_disk_gb": 500},
                "metrics": {"cpu_percent": 30, "memory_percent": 50, "disk_percent": 20, "network_connections": 200},
                "failover": {"enabled": True, "promotion_time_seconds": 15, "health_check_interval_seconds": 3},
                "security": {"encryption_at_rest": True, "encryption_in_transit": True, "backup_enabled": True, "backup_frequency_hours": 0.5, "network_segmented": True, "log_enabled": True, "ids_monitored": True},
                "cost_profile": {"hourly_infra_cost": 3.00},
                "compliance_tags": {"data_classification": "restricted", "pci_scope": True, "contains_pii": True, "audit_logging": True, "change_management": True},
            },
            {
                "id": "hsm-fin",
                "name": "HSM (Key Management)",
                "type": "external_api",
                "replicas": 2,
                "capacity": {"max_connections": 5000, "max_rps": 10000},
                "metrics": {"cpu_percent": 15, "network_connections": 100},
                "failover": {"enabled": True, "promotion_time_seconds": 10},
                "security": {"encryption_at_rest": True, "encryption_in_transit": True, "auth_required": True, "network_segmented": True, "log_enabled": True},
                "cost_profile": {"hourly_infra_cost": 2.00},
            },
            {
                "id": "fin-audit",
                "name": "Financial Audit Trail",
                "type": "storage",
                "replicas": 2,
                "capacity": {"max_disk_gb": 1000},
                "metrics": {"disk_percent": 10},
                "failover": {"enabled": True, "promotion_time_seconds": 10},
                "security": {"encryption_at_rest": True, "encryption_in_transit": True, "backup_enabled": True, "log_enabled": True},
                "cost_profile": {"hourly_infra_cost": 0.50},
                "compliance_tags": {"data_classification": "restricted", "audit_logging": True, "change_management": True},
            },
            {
                "id": "fin-cache",
                "name": "Session/Rate Cache",
                "type": "cache",
                "replicas": 2,
                "capacity": {"max_connections": 10000, "max_memory_mb": 8192},
                "metrics": {"cpu_percent": 10, "memory_percent": 45, "network_connections": 300},
                "failover": {"enabled": True, "promotion_time_seconds": 5},
                "security": {"encryption_in_transit": True, "auth_required": True, "network_segmented": True},
                "cost_profile": {"hourly_infra_cost": 0.60},
            },
        ],
        edges=[
            {"source": "waf-fin", "target": "fin-app", "type": "requires", "protocol": "https", "latency_ms": 2.0, "circuit_breaker": {"enabled": True, "failure_threshold": 3}},
            {"source": "fin-app", "target": "fin-db", "type": "requires", "protocol": "tcp", "latency_ms": 2.0, "circuit_breaker": {"enabled": True, "failure_threshold": 3}, "retry_strategy": {"enabled": True, "max_retries": 3}},
            {"source": "fin-app", "target": "hsm-fin", "type": "requires", "protocol": "tcp", "latency_ms": 5.0, "circuit_breaker": {"enabled": True, "failure_threshold": 2}},
            {"source": "fin-app", "target": "fin-audit", "type": "requires", "protocol": "tcp", "latency_ms": 1.0, "circuit_breaker": {"enabled": True, "failure_threshold": 5}},
            {"source": "fin-app", "target": "fin-cache", "type": "optional", "protocol": "tcp", "latency_ms": 0.5, "weight": 0.7, "circuit_breaker": {"enabled": True, "failure_threshold": 5}},
        ],
        resilience_score=93.0,
        tags=["fintech", "dora", "pci-dss", "banking", "compliance", "hsm"],
        difficulty="expert",
        cloud_provider="aws",
        compliance=["DORA", "PCI_DSS", "SOC2"],
        diagram_mermaid=(
            "graph TD\n"
            "    WAF[WAF / DDoS x2] --> APP[Banking App x4]\n"
            "    APP --> DB[Financial DB x3]\n"
            "    APP --> HSM[HSM x2]\n"
            "    APP --> AUDIT[Audit Trail x2]\n"
            "    APP -.-> CACHE[Session Cache x2]"
        ),
        best_practices=[
            "HSM for all cryptographic operations",
            "Immutable audit trail with tamper detection",
            "WAF with DDoS protection",
            "Regular ICT testing per DORA requirements",
            "Third-party risk isolation via network segmentation",
            "30-minute backup frequency for financial data",
        ],
    ),
    InfraTemplate(
        id="event-driven-saga",
        name="Event-Driven Architecture with Saga Pattern",
        category=TemplateCategory.EVENT_DRIVEN,
        description=(
            "Choreography-based sagas with event store, multiple bounded "
            "contexts, and dead letter queues for reliable event processing."
        ),
        architecture_style="event-driven saga",
        target_nines=3.5,
        estimated_monthly_cost="$4,000-10,000",
        components=[
            {
                "id": "event-gateway",
                "name": "Event Gateway",
                "type": "load_balancer",
                "replicas": 2,
                "capacity": {"max_connections": 30000, "max_rps": 60000},
                "metrics": {"cpu_percent": 15, "memory_percent": 20, "network_connections": 1000},
                "failover": {"enabled": True, "promotion_time_seconds": 5},
                "security": {"encryption_in_transit": True, "auth_required": True, "log_enabled": True},
                "cost_profile": {"hourly_infra_cost": 0.40},
            },
            {
                "id": "event-store",
                "name": "Event Store",
                "type": "database",
                "replicas": 3,
                "capacity": {"max_connections": 1000, "max_disk_gb": 500},
                "metrics": {"cpu_percent": 35, "memory_percent": 50, "disk_percent": 25, "network_connections": 300},
                "failover": {"enabled": True, "promotion_time_seconds": 15},
                "security": {"encryption_at_rest": True, "encryption_in_transit": True, "backup_enabled": True, "backup_frequency_hours": 1, "log_enabled": True},
                "cost_profile": {"hourly_infra_cost": 1.50},
            },
            {
                "id": "svc-inventory",
                "name": "Inventory Service",
                "type": "app_server",
                "replicas": 3,
                "capacity": {"max_connections": 3000, "max_rps": 8000},
                "metrics": {"cpu_percent": 30, "memory_percent": 40, "network_connections": 400},
                "autoscaling": {"enabled": True, "min_replicas": 2, "max_replicas": 8},
                "security": {"encryption_in_transit": True, "log_enabled": True},
                "cost_profile": {"hourly_infra_cost": 0.40},
            },
            {
                "id": "svc-shipping",
                "name": "Shipping Service",
                "type": "app_server",
                "replicas": 2,
                "capacity": {"max_connections": 2000, "max_rps": 5000},
                "metrics": {"cpu_percent": 25, "memory_percent": 35, "network_connections": 200},
                "autoscaling": {"enabled": True, "min_replicas": 1, "max_replicas": 6},
                "security": {"encryption_in_transit": True, "log_enabled": True},
                "cost_profile": {"hourly_infra_cost": 0.30},
            },
            {
                "id": "dlq",
                "name": "Dead Letter Queue",
                "type": "queue",
                "replicas": 2,
                "capacity": {"max_connections": 10000, "max_rps": 50000},
                "metrics": {"cpu_percent": 10, "memory_percent": 15, "network_connections": 50},
                "failover": {"enabled": True, "promotion_time_seconds": 10},
                "security": {"encryption_in_transit": True, "log_enabled": True},
                "cost_profile": {"hourly_infra_cost": 0.20},
            },
        ],
        edges=[
            {"source": "event-gateway", "target": "event-store", "type": "requires", "protocol": "tcp", "latency_ms": 2.0, "circuit_breaker": {"enabled": True, "failure_threshold": 3}},
            {"source": "event-store", "target": "svc-inventory", "type": "async", "protocol": "tcp", "latency_ms": 5.0},
            {"source": "event-store", "target": "svc-shipping", "type": "async", "protocol": "tcp", "latency_ms": 5.0},
            {"source": "svc-inventory", "target": "dlq", "type": "optional", "protocol": "tcp", "latency_ms": 1.0, "weight": 0.3, "circuit_breaker": {"enabled": True, "failure_threshold": 5}},
            {"source": "svc-shipping", "target": "dlq", "type": "optional", "protocol": "tcp", "latency_ms": 1.0, "weight": 0.3},
        ],
        resilience_score=82.0,
        tags=["event-driven", "saga", "cqrs", "event-store", "dlq"],
        difficulty="advanced",
        cloud_provider="cloud-agnostic",
        diagram_mermaid=(
            "graph TD\n"
            "    GW[Event Gateway x2] --> ES[Event Store x3]\n"
            "    ES -.-> INV[Inventory Service x3]\n"
            "    ES -.-> SHIP[Shipping Service x2]\n"
            "    INV -.-> DLQ[Dead Letter Queue x2]\n"
            "    SHIP -.-> DLQ"
        ),
        best_practices=[
            "Event sourcing for full audit trail",
            "Dead letter queues for failed event processing",
            "Idempotent event handlers",
            "Compensating transactions for saga rollback",
            "Event schema versioning",
        ],
    ),
    InfraTemplate(
        id="minimal-startup",
        name="Minimal Startup Stack",
        category=TemplateCategory.WEB_APPLICATION,
        description=(
            "Cost-effective starter stack: single LB, 2 app servers, "
            "managed DB, cache. Good starting point that can grow."
        ),
        architecture_style="minimal 2-tier",
        target_nines=2.5,
        estimated_monthly_cost="$200-500",
        components=[
            {
                "id": "startup-lb",
                "name": "Load Balancer",
                "type": "load_balancer",
                "replicas": 1,
                "capacity": {"max_connections": 5000, "max_rps": 10000},
                "metrics": {"cpu_percent": 10, "memory_percent": 15, "network_connections": 200},
                "security": {"encryption_in_transit": True, "log_enabled": True},
                "cost_profile": {"hourly_infra_cost": 0.05},
            },
            {
                "id": "startup-app",
                "name": "App Server",
                "type": "app_server",
                "replicas": 2,
                "capacity": {"max_connections": 1000, "max_rps": 3000, "timeout_seconds": 30},
                "metrics": {"cpu_percent": 30, "memory_percent": 40, "network_connections": 150},
                "security": {"encryption_in_transit": True, "auth_required": True, "log_enabled": True},
                "cost_profile": {"hourly_infra_cost": 0.10},
            },
            {
                "id": "startup-db",
                "name": "Managed Database",
                "type": "database",
                "replicas": 1,
                "capacity": {"max_connections": 100, "max_disk_gb": 20},
                "metrics": {"cpu_percent": 20, "memory_percent": 35, "disk_percent": 15, "network_connections": 30},
                "security": {"encryption_at_rest": True, "encryption_in_transit": True, "backup_enabled": True, "log_enabled": True},
                "cost_profile": {"hourly_infra_cost": 0.15},
                "compliance_tags": {"data_classification": "internal", "audit_logging": True},
            },
            {
                "id": "startup-cache",
                "name": "Redis Cache",
                "type": "cache",
                "replicas": 1,
                "capacity": {"max_connections": 5000, "max_memory_mb": 1024},
                "metrics": {"cpu_percent": 5, "memory_percent": 30, "network_connections": 50},
                "security": {"encryption_in_transit": True},
                "cost_profile": {"hourly_infra_cost": 0.03},
            },
        ],
        edges=[
            {"source": "startup-lb", "target": "startup-app", "type": "requires", "protocol": "http", "latency_ms": 1.0},
            {"source": "startup-app", "target": "startup-db", "type": "requires", "protocol": "tcp", "latency_ms": 2.0, "retry_strategy": {"enabled": True, "max_retries": 3}},
            {"source": "startup-app", "target": "startup-cache", "type": "optional", "protocol": "tcp", "latency_ms": 0.5, "weight": 0.5},
        ],
        resilience_score=45.0,
        tags=["startup", "minimal", "cost-effective", "mvp"],
        difficulty="starter",
        cloud_provider="cloud-agnostic",
        diagram_mermaid=(
            "graph TD\n"
            "    LB[Load Balancer] --> APP[App Server x2]\n"
            "    APP --> DB[Managed DB]\n"
            "    APP -.-> CACHE[Redis Cache]"
        ),
        best_practices=[
            "Start simple, scale as needed",
            "Use managed database for less operational overhead",
            "Add redundancy and failover as you grow",
            "Monitor metrics to know when to scale",
        ],
    ),
    # ------------------------------------------------------------------
    # AI Agent templates
    # ------------------------------------------------------------------
    InfraTemplate(
        id="ai-chatbot",
        name="AI Chatbot",
        category=TemplateCategory.AI_AGENTS,
        description=(
            "Simple AI chatbot with a single agent backed by an LLM API "
            "and a database for conversation context. Includes circuit "
            "breakers and hallucination safeguards."
        ),
        architecture_style="agent-single",
        target_nines=3.5,
        estimated_monthly_cost="$500-2,000",
        components=[
            {
                "id": "user-gateway",
                "name": "User Gateway",
                "type": "load_balancer",
                "replicas": 2,
                "capacity": {"max_connections": 10000, "max_rps": 20000},
                "metrics": {"cpu_percent": 10, "memory_percent": 15, "network_connections": 500},
                "failover": {"enabled": True, "promotion_time_seconds": 5},
                "security": {"encryption_in_transit": True, "rate_limiting": True, "log_enabled": True},
                "cost_profile": {"hourly_infra_cost": 0.20},
            },
            {
                "id": "chat-agent",
                "name": "Chat Agent",
                "type": "ai_agent",
                "replicas": 2,
                "capacity": {"max_connections": 2000, "max_rps": 500},
                "metrics": {"cpu_percent": 30, "memory_percent": 50, "network_connections": 200},
                "autoscaling": {"enabled": True, "min_replicas": 2, "max_replicas": 8},
                "security": {"encryption_in_transit": True, "log_enabled": True},
                "cost_profile": {"hourly_infra_cost": 0.40},
            },
            {
                "id": "llm-api",
                "name": "LLM API",
                "type": "llm_endpoint",
                "replicas": 1,
                "capacity": {"max_rps": 1000},
                "metrics": {"cpu_percent": 0, "memory_percent": 0, "network_connections": 100},
                "security": {"encryption_in_transit": True, "auth_required": True, "log_enabled": True},
                "cost_profile": {"hourly_infra_cost": 0.0},
            },
            {
                "id": "context-db",
                "name": "Context Database",
                "type": "database",
                "replicas": 2,
                "capacity": {"max_connections": 500, "max_disk_gb": 50},
                "metrics": {"cpu_percent": 20, "memory_percent": 40, "disk_percent": 15, "network_connections": 100},
                "failover": {"enabled": True, "promotion_time_seconds": 30},
                "security": {"encryption_at_rest": True, "encryption_in_transit": True, "backup_enabled": True, "network_segmented": True, "log_enabled": True},
                "cost_profile": {"hourly_infra_cost": 0.80},
                "compliance_tags": {"data_classification": "confidential", "contains_pii": True, "audit_logging": True},
            },
        ],
        edges=[
            {"source": "user-gateway", "target": "chat-agent", "type": "requires", "protocol": "https", "latency_ms": 2.0, "circuit_breaker": {"enabled": True, "failure_threshold": 5}},
            {"source": "chat-agent", "target": "llm-api", "type": "requires", "protocol": "https", "latency_ms": 500.0, "circuit_breaker": {"enabled": True, "failure_threshold": 3}, "retry_strategy": {"enabled": True, "max_retries": 2}},
            {"source": "chat-agent", "target": "context-db", "type": "optional", "protocol": "tcp", "latency_ms": 2.0, "weight": 0.8, "circuit_breaker": {"enabled": True, "failure_threshold": 3}},
        ],
        resilience_score=78.0,
        tags=["ai", "chatbot", "agent", "llm", "conversational"],
        difficulty="starter",
        cloud_provider="cloud-agnostic",
        compliance=["SOC2"],
        diagram_mermaid=(
            "graph TD\n"
            "    GW[User Gateway] --> AGENT[Chat Agent x2]\n"
            "    AGENT --> LLM[LLM API]\n"
            "    AGENT -.-> DB[Context Database x2]"
        ),
        best_practices=[
            "Run at least 2 agent replicas for availability",
            "Circuit breaker on LLM endpoint to handle API outages",
            "Conversation context in DB enables graceful degradation",
            "Rate limiting at gateway to prevent abuse",
            "Enable hallucination detection and logging",
        ],
    ),
    InfraTemplate(
        id="ai-rag-pipeline",
        name="AI RAG Pipeline",
        category=TemplateCategory.AI_AGENTS,
        description=(
            "Retrieval-Augmented Generation pipeline with a router, retriever agent "
            "backed by a vector database, and a writer agent connected to an LLM API. "
            "Designed to reduce hallucination through grounded responses."
        ),
        architecture_style="agent-pipeline",
        target_nines=3.5,
        estimated_monthly_cost="$1,500-5,000",
        components=[
            {
                "id": "rag-gateway",
                "name": "RAG Gateway",
                "type": "load_balancer",
                "replicas": 2,
                "capacity": {"max_connections": 10000, "max_rps": 15000},
                "metrics": {"cpu_percent": 10, "memory_percent": 15, "network_connections": 400},
                "failover": {"enabled": True, "promotion_time_seconds": 5},
                "security": {"encryption_in_transit": True, "rate_limiting": True, "log_enabled": True},
                "cost_profile": {"hourly_infra_cost": 0.20},
            },
            {
                "id": "router",
                "name": "Query Router",
                "type": "agent_orchestrator",
                "replicas": 2,
                "capacity": {"max_connections": 5000, "max_rps": 3000},
                "metrics": {"cpu_percent": 20, "memory_percent": 30, "network_connections": 300},
                "autoscaling": {"enabled": True, "min_replicas": 2, "max_replicas": 6},
                "security": {"encryption_in_transit": True, "log_enabled": True},
                "cost_profile": {"hourly_infra_cost": 0.30},
            },
            {
                "id": "retriever-agent",
                "name": "Retriever Agent",
                "type": "ai_agent",
                "replicas": 2,
                "capacity": {"max_connections": 2000, "max_rps": 1000},
                "metrics": {"cpu_percent": 35, "memory_percent": 55, "network_connections": 200},
                "autoscaling": {"enabled": True, "min_replicas": 2, "max_replicas": 8},
                "security": {"encryption_in_transit": True, "log_enabled": True},
                "cost_profile": {"hourly_infra_cost": 0.40},
            },
            {
                "id": "vector-db",
                "name": "Vector Database",
                "type": "database",
                "replicas": 2,
                "capacity": {"max_connections": 1000, "max_disk_gb": 200},
                "metrics": {"cpu_percent": 40, "memory_percent": 60, "disk_percent": 30, "network_connections": 200},
                "failover": {"enabled": True, "promotion_time_seconds": 30},
                "security": {"encryption_at_rest": True, "encryption_in_transit": True, "backup_enabled": True, "network_segmented": True, "log_enabled": True},
                "cost_profile": {"hourly_infra_cost": 1.50},
            },
            {
                "id": "writer-agent",
                "name": "Writer Agent",
                "type": "ai_agent",
                "replicas": 2,
                "capacity": {"max_connections": 2000, "max_rps": 800},
                "metrics": {"cpu_percent": 30, "memory_percent": 50, "network_connections": 200},
                "autoscaling": {"enabled": True, "min_replicas": 2, "max_replicas": 8},
                "security": {"encryption_in_transit": True, "log_enabled": True},
                "cost_profile": {"hourly_infra_cost": 0.40},
            },
            {
                "id": "rag-llm-api",
                "name": "LLM API",
                "type": "llm_endpoint",
                "replicas": 1,
                "capacity": {"max_rps": 1000},
                "metrics": {"cpu_percent": 0, "memory_percent": 0, "network_connections": 150},
                "security": {"encryption_in_transit": True, "auth_required": True, "log_enabled": True},
                "cost_profile": {"hourly_infra_cost": 0.0},
            },
        ],
        edges=[
            {"source": "rag-gateway", "target": "router", "type": "requires", "protocol": "https", "latency_ms": 2.0, "circuit_breaker": {"enabled": True, "failure_threshold": 5}},
            {"source": "router", "target": "retriever-agent", "type": "requires", "protocol": "grpc", "latency_ms": 5.0, "circuit_breaker": {"enabled": True, "failure_threshold": 3}},
            {"source": "retriever-agent", "target": "vector-db", "type": "requires", "protocol": "tcp", "latency_ms": 3.0, "circuit_breaker": {"enabled": True, "failure_threshold": 3}, "retry_strategy": {"enabled": True, "max_retries": 2}},
            {"source": "router", "target": "writer-agent", "type": "requires", "protocol": "grpc", "latency_ms": 5.0, "circuit_breaker": {"enabled": True, "failure_threshold": 3}},
            {"source": "writer-agent", "target": "rag-llm-api", "type": "requires", "protocol": "https", "latency_ms": 500.0, "circuit_breaker": {"enabled": True, "failure_threshold": 3}, "retry_strategy": {"enabled": True, "max_retries": 2}},
        ],
        resilience_score=82.0,
        tags=["ai", "rag", "agent", "llm", "vector-db", "retrieval"],
        difficulty="intermediate",
        cloud_provider="cloud-agnostic",
        compliance=["SOC2"],
        diagram_mermaid=(
            "graph TD\n"
            "    GW[RAG Gateway] --> ROUTER[Query Router x2]\n"
            "    ROUTER --> RET[Retriever Agent x2]\n"
            "    RET --> VDB[Vector Database x2]\n"
            "    ROUTER --> WRITER[Writer Agent x2]\n"
            "    WRITER --> LLM[LLM API]"
        ),
        best_practices=[
            "Grounding retriever agent in vector DB reduces hallucination",
            "Circuit breakers on all agent-to-service dependencies",
            "Router enables query classification and routing optimisation",
            "Separate retriever and writer agents for independent scaling",
            "Vector DB replication for grounding data availability",
        ],
    ),
    InfraTemplate(
        id="ai-multi-agent",
        name="AI Multi-Agent System",
        category=TemplateCategory.AI_AGENTS,
        description=(
            "Multi-agent system with an orchestrator coordinating research, writer, "
            "and reviewer agents. Each agent connects to LLM APIs and external tools. "
            "Designed for complex content generation and analysis workflows."
        ),
        architecture_style="agent-orchestrated",
        target_nines=3.0,
        estimated_monthly_cost="$3,000-10,000",
        components=[
            {
                "id": "multi-gateway",
                "name": "API Gateway",
                "type": "load_balancer",
                "replicas": 2,
                "capacity": {"max_connections": 10000, "max_rps": 15000},
                "metrics": {"cpu_percent": 10, "memory_percent": 15, "network_connections": 500},
                "failover": {"enabled": True, "promotion_time_seconds": 5},
                "security": {"encryption_in_transit": True, "rate_limiting": True, "log_enabled": True},
                "cost_profile": {"hourly_infra_cost": 0.20},
            },
            {
                "id": "orchestrator",
                "name": "Agent Orchestrator",
                "type": "agent_orchestrator",
                "replicas": 2,
                "capacity": {"max_connections": 3000, "max_rps": 1000},
                "metrics": {"cpu_percent": 25, "memory_percent": 40, "network_connections": 300},
                "autoscaling": {"enabled": True, "min_replicas": 2, "max_replicas": 6},
                "security": {"encryption_in_transit": True, "log_enabled": True},
                "cost_profile": {"hourly_infra_cost": 0.40},
            },
            {
                "id": "research-agent",
                "name": "Research Agent",
                "type": "ai_agent",
                "replicas": 2,
                "capacity": {"max_connections": 1500, "max_rps": 500},
                "metrics": {"cpu_percent": 35, "memory_percent": 55, "network_connections": 150},
                "autoscaling": {"enabled": True, "min_replicas": 2, "max_replicas": 8},
                "security": {"encryption_in_transit": True, "log_enabled": True},
                "cost_profile": {"hourly_infra_cost": 0.40},
            },
            {
                "id": "writer-agent-multi",
                "name": "Writer Agent",
                "type": "ai_agent",
                "replicas": 2,
                "capacity": {"max_connections": 1500, "max_rps": 500},
                "metrics": {"cpu_percent": 30, "memory_percent": 50, "network_connections": 150},
                "autoscaling": {"enabled": True, "min_replicas": 2, "max_replicas": 8},
                "security": {"encryption_in_transit": True, "log_enabled": True},
                "cost_profile": {"hourly_infra_cost": 0.40},
            },
            {
                "id": "reviewer-agent",
                "name": "Reviewer Agent",
                "type": "ai_agent",
                "replicas": 2,
                "capacity": {"max_connections": 1500, "max_rps": 500},
                "metrics": {"cpu_percent": 25, "memory_percent": 45, "network_connections": 100},
                "autoscaling": {"enabled": True, "min_replicas": 1, "max_replicas": 4},
                "security": {"encryption_in_transit": True, "log_enabled": True},
                "cost_profile": {"hourly_infra_cost": 0.40},
            },
            {
                "id": "multi-llm-primary",
                "name": "Primary LLM API",
                "type": "llm_endpoint",
                "replicas": 1,
                "capacity": {"max_rps": 1000},
                "metrics": {"cpu_percent": 0, "memory_percent": 0, "network_connections": 200},
                "security": {"encryption_in_transit": True, "auth_required": True, "log_enabled": True},
                "cost_profile": {"hourly_infra_cost": 0.0},
            },
            {
                "id": "multi-llm-secondary",
                "name": "Secondary LLM API",
                "type": "llm_endpoint",
                "replicas": 1,
                "capacity": {"max_rps": 500},
                "metrics": {"cpu_percent": 0, "memory_percent": 0, "network_connections": 100},
                "security": {"encryption_in_transit": True, "auth_required": True, "log_enabled": True},
                "cost_profile": {"hourly_infra_cost": 0.0},
            },
            {
                "id": "search-tool",
                "name": "Search Tool",
                "type": "tool_service",
                "replicas": 2,
                "capacity": {"max_connections": 5000, "max_rps": 3000},
                "metrics": {"cpu_percent": 20, "memory_percent": 30, "network_connections": 200},
                "security": {"encryption_in_transit": True, "auth_required": True, "log_enabled": True},
                "cost_profile": {"hourly_infra_cost": 0.30},
            },
            {
                "id": "code-exec-tool",
                "name": "Code Execution Tool",
                "type": "tool_service",
                "replicas": 2,
                "capacity": {"max_connections": 1000, "max_rps": 500},
                "metrics": {"cpu_percent": 40, "memory_percent": 50, "network_connections": 80},
                "security": {"encryption_in_transit": True, "auth_required": True, "network_segmented": True, "log_enabled": True},
                "cost_profile": {"hourly_infra_cost": 0.50},
            },
        ],
        edges=[
            {"source": "multi-gateway", "target": "orchestrator", "type": "requires", "protocol": "https", "latency_ms": 2.0, "circuit_breaker": {"enabled": True, "failure_threshold": 5}},
            {"source": "orchestrator", "target": "research-agent", "type": "requires", "protocol": "grpc", "latency_ms": 5.0, "circuit_breaker": {"enabled": True, "failure_threshold": 3}},
            {"source": "orchestrator", "target": "writer-agent-multi", "type": "requires", "protocol": "grpc", "latency_ms": 5.0, "circuit_breaker": {"enabled": True, "failure_threshold": 3}},
            {"source": "orchestrator", "target": "reviewer-agent", "type": "requires", "protocol": "grpc", "latency_ms": 5.0, "circuit_breaker": {"enabled": True, "failure_threshold": 3}},
            {"source": "research-agent", "target": "multi-llm-primary", "type": "requires", "protocol": "https", "latency_ms": 500.0, "circuit_breaker": {"enabled": True, "failure_threshold": 3}, "retry_strategy": {"enabled": True, "max_retries": 2}},
            {"source": "research-agent", "target": "search-tool", "type": "optional", "protocol": "https", "latency_ms": 50.0, "weight": 0.8, "circuit_breaker": {"enabled": True, "failure_threshold": 5}},
            {"source": "writer-agent-multi", "target": "multi-llm-primary", "type": "requires", "protocol": "https", "latency_ms": 500.0, "circuit_breaker": {"enabled": True, "failure_threshold": 3}, "retry_strategy": {"enabled": True, "max_retries": 2}},
            {"source": "reviewer-agent", "target": "multi-llm-secondary", "type": "requires", "protocol": "https", "latency_ms": 500.0, "circuit_breaker": {"enabled": True, "failure_threshold": 3}, "retry_strategy": {"enabled": True, "max_retries": 2}},
            {"source": "reviewer-agent", "target": "code-exec-tool", "type": "optional", "protocol": "https", "latency_ms": 100.0, "weight": 0.6, "circuit_breaker": {"enabled": True, "failure_threshold": 5}},
        ],
        resilience_score=80.0,
        tags=["ai", "multi-agent", "orchestrator", "llm", "tools", "research"],
        difficulty="advanced",
        cloud_provider="cloud-agnostic",
        compliance=["SOC2"],
        diagram_mermaid=(
            "graph TD\n"
            "    GW[API Gateway] --> ORCH[Orchestrator x2]\n"
            "    ORCH --> RES[Research Agent x2]\n"
            "    ORCH --> WRT[Writer Agent x2]\n"
            "    ORCH --> REV[Reviewer Agent x2]\n"
            "    RES --> LLM1[Primary LLM API]\n"
            "    RES -.-> SEARCH[Search Tool x2]\n"
            "    WRT --> LLM1\n"
            "    REV --> LLM2[Secondary LLM API]\n"
            "    REV -.-> CODE[Code Execution Tool x2]"
        ),
        best_practices=[
            "Use separate LLM endpoints for reviewer to avoid single provider dependency",
            "Orchestrator with iteration limits to prevent infinite agent loops",
            "Circuit breakers on all agent-to-LLM and agent-to-tool connections",
            "Tool services should be sandboxed (especially code execution)",
            "Auto-scaling agents independently based on workload patterns",
            "Add human escalation path for high-stakes decisions",
        ],
    ),
    InfraTemplate(
        id="ai-customer-support",
        name="AI Customer Support Bot",
        category=TemplateCategory.AI_AGENTS,
        description=(
            "Customer support system with a triage agent that routes queries "
            "to FAQ and escalation agents. Integrates with CRM and ticketing "
            "tools for automated support workflows."
        ),
        architecture_style="agent-triage",
        target_nines=3.5,
        estimated_monthly_cost="$2,000-6,000",
        components=[
            {
                "id": "support-gateway",
                "name": "Support Gateway",
                "type": "load_balancer",
                "replicas": 2,
                "capacity": {"max_connections": 15000, "max_rps": 20000},
                "metrics": {"cpu_percent": 10, "memory_percent": 15, "network_connections": 600},
                "failover": {"enabled": True, "promotion_time_seconds": 5},
                "security": {"encryption_in_transit": True, "rate_limiting": True, "log_enabled": True},
                "cost_profile": {"hourly_infra_cost": 0.20},
            },
            {
                "id": "triage-agent",
                "name": "Triage Agent",
                "type": "agent_orchestrator",
                "replicas": 2,
                "capacity": {"max_connections": 5000, "max_rps": 2000},
                "metrics": {"cpu_percent": 20, "memory_percent": 35, "network_connections": 400},
                "autoscaling": {"enabled": True, "min_replicas": 2, "max_replicas": 8},
                "security": {"encryption_in_transit": True, "log_enabled": True},
                "cost_profile": {"hourly_infra_cost": 0.40},
            },
            {
                "id": "faq-agent",
                "name": "FAQ Agent",
                "type": "ai_agent",
                "replicas": 2,
                "capacity": {"max_connections": 3000, "max_rps": 1500},
                "metrics": {"cpu_percent": 25, "memory_percent": 45, "network_connections": 200},
                "autoscaling": {"enabled": True, "min_replicas": 2, "max_replicas": 10},
                "security": {"encryption_in_transit": True, "log_enabled": True},
                "cost_profile": {"hourly_infra_cost": 0.30},
            },
            {
                "id": "escalation-agent",
                "name": "Escalation Agent",
                "type": "ai_agent",
                "replicas": 2,
                "capacity": {"max_connections": 2000, "max_rps": 800},
                "metrics": {"cpu_percent": 30, "memory_percent": 50, "network_connections": 150},
                "autoscaling": {"enabled": True, "min_replicas": 1, "max_replicas": 6},
                "security": {"encryption_in_transit": True, "log_enabled": True},
                "cost_profile": {"hourly_infra_cost": 0.40},
            },
            {
                "id": "support-llm-api",
                "name": "LLM API",
                "type": "llm_endpoint",
                "replicas": 1,
                "capacity": {"max_rps": 2000},
                "metrics": {"cpu_percent": 0, "memory_percent": 0, "network_connections": 200},
                "security": {"encryption_in_transit": True, "auth_required": True, "log_enabled": True},
                "cost_profile": {"hourly_infra_cost": 0.0},
            },
            {
                "id": "crm-tool",
                "name": "CRM Tool",
                "type": "tool_service",
                "replicas": 2,
                "capacity": {"max_connections": 5000, "max_rps": 3000},
                "metrics": {"cpu_percent": 15, "memory_percent": 25, "network_connections": 200},
                "security": {"encryption_in_transit": True, "auth_required": True, "log_enabled": True},
                "cost_profile": {"hourly_infra_cost": 0.25},
            },
            {
                "id": "ticket-tool",
                "name": "Ticket Tool",
                "type": "tool_service",
                "replicas": 2,
                "capacity": {"max_connections": 3000, "max_rps": 2000},
                "metrics": {"cpu_percent": 15, "memory_percent": 25, "network_connections": 150},
                "security": {"encryption_in_transit": True, "auth_required": True, "log_enabled": True},
                "cost_profile": {"hourly_infra_cost": 0.25},
            },
        ],
        edges=[
            {"source": "support-gateway", "target": "triage-agent", "type": "requires", "protocol": "https", "latency_ms": 2.0, "circuit_breaker": {"enabled": True, "failure_threshold": 5}},
            {"source": "triage-agent", "target": "faq-agent", "type": "requires", "protocol": "grpc", "latency_ms": 5.0, "circuit_breaker": {"enabled": True, "failure_threshold": 3}},
            {"source": "triage-agent", "target": "escalation-agent", "type": "requires", "protocol": "grpc", "latency_ms": 5.0, "circuit_breaker": {"enabled": True, "failure_threshold": 3}},
            {"source": "faq-agent", "target": "support-llm-api", "type": "requires", "protocol": "https", "latency_ms": 500.0, "circuit_breaker": {"enabled": True, "failure_threshold": 3}, "retry_strategy": {"enabled": True, "max_retries": 2}},
            {"source": "escalation-agent", "target": "support-llm-api", "type": "requires", "protocol": "https", "latency_ms": 500.0, "circuit_breaker": {"enabled": True, "failure_threshold": 3}, "retry_strategy": {"enabled": True, "max_retries": 2}},
            {"source": "faq-agent", "target": "crm-tool", "type": "optional", "protocol": "https", "latency_ms": 20.0, "weight": 0.7, "circuit_breaker": {"enabled": True, "failure_threshold": 5}},
            {"source": "escalation-agent", "target": "crm-tool", "type": "requires", "protocol": "https", "latency_ms": 20.0, "circuit_breaker": {"enabled": True, "failure_threshold": 3}},
            {"source": "escalation-agent", "target": "ticket-tool", "type": "requires", "protocol": "https", "latency_ms": 20.0, "circuit_breaker": {"enabled": True, "failure_threshold": 3}},
        ],
        resilience_score=81.0,
        tags=["ai", "customer-support", "agent", "triage", "crm", "ticketing"],
        difficulty="intermediate",
        cloud_provider="cloud-agnostic",
        compliance=["SOC2", "GDPR"],
        diagram_mermaid=(
            "graph TD\n"
            "    GW[Support Gateway] --> TRIAGE[Triage Agent x2]\n"
            "    TRIAGE --> FAQ[FAQ Agent x2]\n"
            "    TRIAGE --> ESC[Escalation Agent x2]\n"
            "    FAQ --> LLM[LLM API]\n"
            "    ESC --> LLM\n"
            "    FAQ -.-> CRM[CRM Tool x2]\n"
            "    ESC --> CRM\n"
            "    ESC --> TICKET[Ticket Tool x2]"
        ),
        best_practices=[
            "Triage agent classifies and routes to minimize LLM costs",
            "FAQ agent handles common queries; escalation agent for complex cases",
            "CRM integration grounds agent responses in customer data",
            "Ticket tool integration enables automatic case creation",
            "Circuit breakers prevent tool failures from cascading to agents",
            "Human escalation path from escalation agent for unresolvable cases",
        ],
    ),
]

# Build lookup by id
_TEMPLATE_BY_ID: dict[str, InfraTemplate] = {t.id: t for t in GALLERY_TEMPLATES}


# ---------------------------------------------------------------------------
# Gallery class
# ---------------------------------------------------------------------------


class TemplateGallery:
    """Access and manage the template gallery."""

    def __init__(self) -> None:
        self._templates = list(GALLERY_TEMPLATES)
        self._by_id = dict(_TEMPLATE_BY_ID)

    def list_templates(self, category: str | None = None) -> list[InfraTemplate]:
        """List all templates, optionally filtered by category."""
        if category is None:
            return list(self._templates)
        cat_lower = category.lower()
        return [
            t for t in self._templates
            if t.category.value == cat_lower or t.category.name.lower() == cat_lower
        ]

    def get_template(self, template_id: str) -> InfraTemplate:
        """Get a template by its ID.

        Raises:
            KeyError: If the template ID is not found.
        """
        if template_id not in self._by_id:
            raise KeyError(
                f"Unknown template '{template_id}'. "
                f"Available: {list(self._by_id.keys())}"
            )
        return self._by_id[template_id]

    def search(self, query: str) -> list[InfraTemplate]:
        """Search templates by name, description, or tags."""
        q = query.lower()
        results: list[InfraTemplate] = []
        for t in self._templates:
            text = f"{t.name} {t.description} {' '.join(t.tags)} {t.category.value}"
            if q in text.lower():
                results.append(t)
        return results

    def instantiate(self, template_id: str) -> InfraGraph:
        """Create an InfraGraph from a template.

        Returns:
            A fully constructed InfraGraph ready for simulation.
        """
        template = self.get_template(template_id)
        return _build_graph_from_template(template)

    def to_yaml(self, template_id: str) -> str:
        """Export a template as YAML configuration."""
        template = self.get_template(template_id)
        data = _template_to_yaml_dict(template)
        return yaml.dump(data, default_flow_style=False, sort_keys=False, allow_unicode=True)

    def compare_with(self, template_id: str, user_graph: InfraGraph) -> dict:
        """Compare a user's infrastructure against a template.

        Returns a dict with comparison metrics including score differences,
        component gaps, and recommendations.
        """
        template = self.get_template(template_id)
        template_graph = _build_graph_from_template(template)

        user_score_data = user_graph.resilience_score_v2()
        template_score_data = template_graph.resilience_score_v2()

        user_score = user_score_data["score"]
        template_score = template_score_data["score"]

        # Component type comparison
        user_types: dict[str, int] = {}
        for c in user_graph.components.values():
            user_types[c.type.value] = user_types.get(c.type.value, 0) + 1

        template_types: dict[str, int] = {}
        for c in template_graph.components.values():
            template_types[c.type.value] = template_types.get(c.type.value, 0) + 1

        missing_types = [t for t in template_types if t not in user_types]
        extra_types = [t for t in user_types if t not in template_types]

        # Feature comparison
        user_failover = sum(1 for c in user_graph.components.values() if c.failover.enabled)
        template_failover = sum(1 for c in template_graph.components.values() if c.failover.enabled)

        user_cb = sum(1 for e in user_graph.all_dependency_edges() if e.circuit_breaker.enabled)
        template_cb = sum(1 for e in template_graph.all_dependency_edges() if e.circuit_breaker.enabled)

        user_as = sum(1 for c in user_graph.components.values() if c.autoscaling.enabled)
        template_as = sum(1 for c in template_graph.components.values() if c.autoscaling.enabled)

        recommendations: list[str] = []
        if user_score < template_score:
            recommendations.append(
                f"Your resilience score ({user_score:.1f}) is below the template reference ({template_score:.1f})."
            )
        if user_failover < template_failover:
            recommendations.append(
                f"Consider adding failover: your infra has {user_failover} vs template's {template_failover}."
            )
        if user_cb < template_cb:
            recommendations.append(
                f"Add circuit breakers: your infra has {user_cb} vs template's {template_cb}."
            )
        if user_as < template_as:
            recommendations.append(
                f"Enable auto-scaling: your infra has {user_as} vs template's {template_as}."
            )
        for mt in missing_types:
            recommendations.append(f"Template includes '{mt}' component type not present in your infra.")

        return {
            "template_id": template_id,
            "template_name": template.name,
            "user_score": user_score,
            "template_score": template_score,
            "score_gap": round(template_score - user_score, 1),
            "user_breakdown": user_score_data["breakdown"],
            "template_breakdown": template_score_data["breakdown"],
            "component_comparison": {
                "user_count": len(user_graph.components),
                "template_count": len(template_graph.components),
                "user_types": user_types,
                "template_types": template_types,
                "missing_types": missing_types,
                "extra_types": extra_types,
            },
            "feature_comparison": {
                "failover": {"user": user_failover, "template": template_failover},
                "circuit_breakers": {"user": user_cb, "template": template_cb},
                "autoscaling": {"user": user_as, "template": template_as},
            },
            "recommendations": recommendations,
        }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _build_component(comp_dict: dict) -> Component:
    """Build a Component from a template component dict."""
    comp_type = ComponentType(comp_dict.get("type", "custom"))

    kwargs: dict[str, Any] = {
        "id": comp_dict["id"],
        "name": comp_dict["name"],
        "type": comp_type,
        "replicas": comp_dict.get("replicas", 1),
    }

    if "capacity" in comp_dict:
        kwargs["capacity"] = Capacity(**comp_dict["capacity"])
    if "metrics" in comp_dict:
        kwargs["metrics"] = ResourceMetrics(**comp_dict["metrics"])
    if "autoscaling" in comp_dict:
        kwargs["autoscaling"] = AutoScalingConfig(**comp_dict["autoscaling"])
    if "failover" in comp_dict:
        kwargs["failover"] = FailoverConfig(**comp_dict["failover"])
    if "security" in comp_dict:
        kwargs["security"] = SecurityProfile(**comp_dict["security"])
    if "cost_profile" in comp_dict:
        kwargs["cost_profile"] = CostProfile(**comp_dict["cost_profile"])
    if "compliance_tags" in comp_dict:
        kwargs["compliance_tags"] = ComplianceTags(**comp_dict["compliance_tags"])

    return Component(**kwargs)


def _build_dependency(edge_dict: dict) -> Dependency:
    """Build a Dependency from a template edge dict."""
    kwargs: dict[str, Any] = {
        "source_id": edge_dict["source"],
        "target_id": edge_dict["target"],
        "dependency_type": edge_dict.get("type", "requires"),
    }
    if "protocol" in edge_dict:
        kwargs["protocol"] = edge_dict["protocol"]
    if "latency_ms" in edge_dict:
        kwargs["latency_ms"] = edge_dict["latency_ms"]
    if "weight" in edge_dict:
        kwargs["weight"] = edge_dict["weight"]
    if "circuit_breaker" in edge_dict:
        kwargs["circuit_breaker"] = CircuitBreakerConfig(**edge_dict["circuit_breaker"])
    if "retry_strategy" in edge_dict:
        kwargs["retry_strategy"] = RetryStrategy(**edge_dict["retry_strategy"])
    return Dependency(**kwargs)


def _build_graph_from_template(template: InfraTemplate) -> InfraGraph:
    """Build an InfraGraph from an InfraTemplate."""
    graph = InfraGraph()
    for comp_dict in template.components:
        graph.add_component(_build_component(comp_dict))
    for edge_dict in template.edges:
        graph.add_dependency(_build_dependency(edge_dict))
    return graph


def _template_to_yaml_dict(template: InfraTemplate) -> dict:
    """Convert a template to a YAML-compatible dict."""
    components: list[dict] = []
    for comp in template.components:
        entry: dict[str, Any] = {
            "id": comp["id"],
            "name": comp["name"],
            "type": comp["type"],
            "replicas": comp.get("replicas", 1),
        }
        for key in ("capacity", "metrics", "autoscaling", "failover", "security",
                     "cost_profile", "compliance_tags"):
            if key in comp:
                entry[key] = comp[key]
        components.append(entry)

    dependencies: list[dict] = []
    for edge in template.edges:
        dep: dict[str, Any] = {
            "source": edge["source"],
            "target": edge["target"],
            "type": edge.get("type", "requires"),
        }
        for key in ("protocol", "latency_ms", "weight", "circuit_breaker", "retry_strategy"):
            if key in edge:
                dep[key] = edge[key]
        dependencies.append(dep)

    return {
        "schema_version": "3.0",
        "components": components,
        "dependencies": dependencies,
    }
