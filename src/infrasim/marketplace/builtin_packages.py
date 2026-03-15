"""Built-in chaos scenario packages for the ChaosProof Marketplace.

Each package contains 3-5 scenario definitions that map to ChaosProof's
FaultType and Scenario model.  These packages are always available without
any network access.
"""

from __future__ import annotations

from datetime import datetime, timezone

from infrasim.marketplace.catalog import ScenarioPackage

# ---------------------------------------------------------------------------
# Helper: fixed timestamp for built-in packages
# ---------------------------------------------------------------------------
_CREATED = datetime(2025, 1, 15, tzinfo=timezone.utc)
_UPDATED = datetime(2026, 3, 1, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# 1. AWS Region Failover Suite
# ---------------------------------------------------------------------------
_aws_region_failover = ScenarioPackage(
    id="aws-region-failover",
    name="AWS Region Failover Suite",
    version="2.0.0",
    description=(
        "Comprehensive region failover scenarios including AZ isolation, "
        "cross-region failover, and Route53 health check failures"
    ),
    author="ChaosProof Team",
    category="disaster_recovery",
    provider="aws",
    severity="critical",
    tags=["aws", "region", "failover", "dr", "multi-region"],
    scenarios=[
        {
            "name": "AZ Isolation",
            "description": "Simulate an entire Availability Zone becoming unreachable",
            "faults": [
                {
                    "target_component_id": "az-primary",
                    "fault_type": "network_partition",
                    "severity": 1.0,
                    "duration_seconds": 600,
                    "_required_type": "app_server",
                    "parameters": {"partition_scope": "az"},
                },
                {
                    "target_component_id": "db-primary",
                    "fault_type": "component_down",
                    "severity": 1.0,
                    "duration_seconds": 600,
                    "_required_type": "database",
                },
            ],
            "traffic_multiplier": 1.0,
        },
        {
            "name": "Region DNS Failover",
            "description": "Route53 health check failure triggering cross-region DNS failover",
            "faults": [
                {
                    "target_component_id": "dns-primary",
                    "fault_type": "component_down",
                    "severity": 1.0,
                    "duration_seconds": 300,
                    "_required_type": "dns",
                },
            ],
            "traffic_multiplier": 1.5,
        },
        {
            "name": "Cross-Region Replication Lag",
            "description": "Database replication lag exceeding acceptable thresholds",
            "faults": [
                {
                    "target_component_id": "db-replica",
                    "fault_type": "latency_spike",
                    "severity": 0.8,
                    "duration_seconds": 900,
                    "_required_type": "database",
                    "parameters": {"latency_ms": 5000},
                },
            ],
            "traffic_multiplier": 1.0,
        },
        {
            "name": "Multi-AZ Database Failover",
            "description": "Primary RDS instance failure forcing automatic failover to standby",
            "faults": [
                {
                    "target_component_id": "db-primary",
                    "fault_type": "component_down",
                    "severity": 1.0,
                    "duration_seconds": 120,
                    "_required_type": "database",
                },
            ],
            "traffic_multiplier": 1.2,
        },
    ],
    prerequisites=["database", "app_server", "dns"],
    estimated_duration="1hr",
    difficulty="advanced",
    created_at=_CREATED,
    updated_at=_UPDATED,
    downloads=3420,
    rating=4.7,
    featured=True,
)


# ---------------------------------------------------------------------------
# 2. AWS Database Chaos Pack
# ---------------------------------------------------------------------------
_aws_database_chaos = ScenarioPackage(
    id="aws-database-chaos",
    name="AWS Database Chaos Pack",
    version="1.5.0",
    description=(
        "Database failure scenarios: storage full, replication lag, "
        "failover testing, connection pool exhaustion"
    ),
    author="ChaosProof Team",
    category="infrastructure",
    provider="aws",
    severity="high",
    tags=["aws", "database", "rds", "aurora", "storage"],
    scenarios=[
        {
            "name": "Database Storage Full",
            "description": "RDS storage volume reaches 100% capacity",
            "faults": [
                {
                    "target_component_id": "db-primary",
                    "fault_type": "disk_full",
                    "severity": 1.0,
                    "duration_seconds": 300,
                    "_required_type": "database",
                },
            ],
            "traffic_multiplier": 1.0,
        },
        {
            "name": "Connection Pool Exhaustion",
            "description": "All database connections consumed by long-running queries",
            "faults": [
                {
                    "target_component_id": "db-primary",
                    "fault_type": "connection_pool_exhaustion",
                    "severity": 0.9,
                    "duration_seconds": 600,
                    "_required_type": "database",
                },
            ],
            "traffic_multiplier": 2.0,
        },
        {
            "name": "Replication Lag Spike",
            "description": "Read replica falls behind primary by several minutes",
            "faults": [
                {
                    "target_component_id": "db-replica",
                    "fault_type": "latency_spike",
                    "severity": 0.7,
                    "duration_seconds": 1200,
                    "_required_type": "database",
                    "parameters": {"latency_ms": 30000},
                },
            ],
            "traffic_multiplier": 1.0,
        },
        {
            "name": "Database CPU Saturation",
            "description": "RDS instance CPU saturated by unoptimized queries",
            "faults": [
                {
                    "target_component_id": "db-primary",
                    "fault_type": "cpu_saturation",
                    "severity": 0.85,
                    "duration_seconds": 900,
                    "_required_type": "database",
                },
            ],
            "traffic_multiplier": 1.5,
        },
    ],
    prerequisites=["database"],
    estimated_duration="30min",
    difficulty="intermediate",
    created_at=_CREATED,
    updated_at=_UPDATED,
    downloads=2890,
    rating=4.5,
    featured=True,
)


# ---------------------------------------------------------------------------
# 3. Kubernetes Pod Disruption Bundle
# ---------------------------------------------------------------------------
_kubernetes_pod_disruption = ScenarioPackage(
    id="kubernetes-pod-disruption",
    name="Kubernetes Pod Disruption Bundle",
    version="2.1.0",
    description=(
        "Pod eviction, node drain, resource quota, OOM kill, "
        "liveness probe failure scenarios"
    ),
    author="ChaosProof Team",
    category="infrastructure",
    provider="kubernetes",
    severity="high",
    tags=["kubernetes", "k8s", "pod", "eviction", "oom", "node-drain"],
    scenarios=[
        {
            "name": "Pod OOM Kill",
            "description": "Container killed by OOM killer due to memory limit exceeded",
            "faults": [
                {
                    "target_component_id": "app-pod",
                    "fault_type": "memory_exhaustion",
                    "severity": 1.0,
                    "duration_seconds": 60,
                    "_required_type": "app_server",
                },
            ],
            "traffic_multiplier": 1.0,
        },
        {
            "name": "Node Drain",
            "description": "Kubernetes node drained for maintenance, pods evicted",
            "faults": [
                {
                    "target_component_id": "app-pod-1",
                    "fault_type": "component_down",
                    "severity": 1.0,
                    "duration_seconds": 120,
                    "_required_type": "app_server",
                },
                {
                    "target_component_id": "app-pod-2",
                    "fault_type": "component_down",
                    "severity": 1.0,
                    "duration_seconds": 120,
                    "_required_type": "app_server",
                },
            ],
            "traffic_multiplier": 1.0,
        },
        {
            "name": "Liveness Probe Failure",
            "description": "Liveness probe fails causing container restart loop",
            "faults": [
                {
                    "target_component_id": "app-pod",
                    "fault_type": "component_down",
                    "severity": 0.8,
                    "duration_seconds": 300,
                    "_required_type": "app_server",
                    "parameters": {"restart_count": 5},
                },
            ],
            "traffic_multiplier": 1.0,
        },
        {
            "name": "Resource Quota Exceeded",
            "description": "Namespace resource quota prevents new pod scheduling",
            "faults": [
                {
                    "target_component_id": "app-pod",
                    "fault_type": "cpu_saturation",
                    "severity": 0.9,
                    "duration_seconds": 600,
                    "_required_type": "app_server",
                },
                {
                    "target_component_id": "app-pod",
                    "fault_type": "memory_exhaustion",
                    "severity": 0.9,
                    "duration_seconds": 600,
                    "_required_type": "app_server",
                },
            ],
            "traffic_multiplier": 1.0,
        },
    ],
    prerequisites=["app_server"],
    estimated_duration="30min",
    difficulty="intermediate",
    created_at=_CREATED,
    updated_at=_UPDATED,
    downloads=4210,
    rating=4.8,
    featured=True,
)


# ---------------------------------------------------------------------------
# 4. Security Attack Simulation Suite
# ---------------------------------------------------------------------------
_security_attack_simulation = ScenarioPackage(
    id="security-attack-simulation",
    name="Security Attack Simulation Suite",
    version="1.3.0",
    description=(
        "Simulate DDoS, credential stuffing, SQL injection impact, "
        "API abuse, and data exfiltration scenarios"
    ),
    author="ChaosProof Team",
    category="security",
    provider="generic",
    severity="critical",
    tags=["security", "ddos", "attack", "api-abuse", "exfiltration"],
    scenarios=[
        {
            "name": "DDoS Traffic Flood",
            "description": "Volumetric DDoS attack overwhelming load balancers",
            "faults": [
                {
                    "target_component_id": "lb-primary",
                    "fault_type": "cpu_saturation",
                    "severity": 0.95,
                    "duration_seconds": 600,
                    "_required_type": "load_balancer",
                },
            ],
            "traffic_multiplier": 10.0,
        },
        {
            "name": "API Rate Limit Bypass",
            "description": "API abuse exhausting backend resources through rate limit evasion",
            "faults": [
                {
                    "target_component_id": "app-server",
                    "fault_type": "connection_pool_exhaustion",
                    "severity": 0.8,
                    "duration_seconds": 900,
                    "_required_type": "app_server",
                },
            ],
            "traffic_multiplier": 5.0,
        },
        {
            "name": "Credential Stuffing Impact",
            "description": "High-volume credential stuffing attack impacting authentication service",
            "faults": [
                {
                    "target_component_id": "auth-service",
                    "fault_type": "cpu_saturation",
                    "severity": 0.7,
                    "duration_seconds": 1800,
                    "_required_type": "app_server",
                },
                {
                    "target_component_id": "db-auth",
                    "fault_type": "connection_pool_exhaustion",
                    "severity": 0.6,
                    "duration_seconds": 1800,
                    "_required_type": "database",
                },
            ],
            "traffic_multiplier": 3.0,
        },
    ],
    prerequisites=["load_balancer", "app_server"],
    estimated_duration="1hr",
    difficulty="advanced",
    created_at=_CREATED,
    updated_at=_UPDATED,
    downloads=1950,
    rating=4.4,
    featured=False,
)


# ---------------------------------------------------------------------------
# 5. Network Chaos Engineering Pack
# ---------------------------------------------------------------------------
_network_chaos_pack = ScenarioPackage(
    id="network-chaos-pack",
    name="Network Chaos Engineering Pack",
    version="1.8.0",
    description=(
        "Network partition, latency injection, packet loss, DNS failure, "
        "TLS certificate expiry"
    ),
    author="ChaosProof Team",
    category="infrastructure",
    provider="generic",
    severity="high",
    tags=["network", "partition", "latency", "dns", "tls", "packet-loss"],
    scenarios=[
        {
            "name": "Network Partition",
            "description": "Network split isolating application tier from database tier",
            "faults": [
                {
                    "target_component_id": "app-server",
                    "fault_type": "network_partition",
                    "severity": 1.0,
                    "duration_seconds": 300,
                    "_required_type": "app_server",
                },
            ],
            "traffic_multiplier": 1.0,
        },
        {
            "name": "Latency Injection",
            "description": "500ms+ latency added to all cross-service communication",
            "faults": [
                {
                    "target_component_id": "app-server",
                    "fault_type": "latency_spike",
                    "severity": 0.6,
                    "duration_seconds": 600,
                    "_required_type": "app_server",
                    "parameters": {"latency_ms": 500},
                },
            ],
            "traffic_multiplier": 1.0,
        },
        {
            "name": "DNS Resolution Failure",
            "description": "DNS server becomes unreachable affecting service discovery",
            "faults": [
                {
                    "target_component_id": "dns-server",
                    "fault_type": "component_down",
                    "severity": 1.0,
                    "duration_seconds": 180,
                    "_required_type": "dns",
                },
            ],
            "traffic_multiplier": 1.0,
        },
        {
            "name": "TLS Certificate Expiry",
            "description": "TLS certificate expires causing connection rejections",
            "faults": [
                {
                    "target_component_id": "lb-primary",
                    "fault_type": "component_down",
                    "severity": 0.9,
                    "duration_seconds": 3600,
                    "_required_type": "load_balancer",
                    "parameters": {"reason": "tls_cert_expired"},
                },
            ],
            "traffic_multiplier": 1.0,
        },
        {
            "name": "Packet Loss Injection",
            "description": "10% packet loss on inter-service communication",
            "faults": [
                {
                    "target_component_id": "app-server",
                    "fault_type": "latency_spike",
                    "severity": 0.4,
                    "duration_seconds": 600,
                    "_required_type": "app_server",
                    "parameters": {"packet_loss_pct": 10},
                },
            ],
            "traffic_multiplier": 1.0,
        },
    ],
    prerequisites=["app_server", "load_balancer"],
    estimated_duration="30min",
    difficulty="intermediate",
    created_at=_CREATED,
    updated_at=_UPDATED,
    downloads=3150,
    rating=4.6,
    featured=True,
)


# ---------------------------------------------------------------------------
# 6. DORA Compliance Validation Suite
# ---------------------------------------------------------------------------
_compliance_dora = ScenarioPackage(
    id="compliance-validation-dora",
    name="DORA Compliance Validation Suite",
    version="1.2.0",
    description=(
        "Scenarios designed to test DORA (Digital Operational Resilience Act) "
        "compliance requirements for financial institutions"
    ),
    author="ChaosProof Team",
    category="compliance",
    provider="generic",
    severity="critical",
    tags=["compliance", "dora", "finance", "regulation", "eu"],
    scenarios=[
        {
            "name": "ICT Service Disruption (DORA Art. 11)",
            "description": "Major ICT service provider outage testing business continuity",
            "faults": [
                {
                    "target_component_id": "external-api",
                    "fault_type": "component_down",
                    "severity": 1.0,
                    "duration_seconds": 3600,
                    "_required_type": "external_api",
                },
            ],
            "traffic_multiplier": 1.0,
        },
        {
            "name": "Data Integrity Verification (DORA Art. 9)",
            "description": "Database corruption scenario to test data integrity checks",
            "faults": [
                {
                    "target_component_id": "db-primary",
                    "fault_type": "disk_full",
                    "severity": 0.7,
                    "duration_seconds": 1800,
                    "_required_type": "database",
                },
            ],
            "traffic_multiplier": 1.0,
        },
        {
            "name": "Backup & Recovery Test (DORA Art. 12)",
            "description": "Full system recovery from backup after complete data loss",
            "faults": [
                {
                    "target_component_id": "db-primary",
                    "fault_type": "component_down",
                    "severity": 1.0,
                    "duration_seconds": 7200,
                    "_required_type": "database",
                },
                {
                    "target_component_id": "storage-primary",
                    "fault_type": "component_down",
                    "severity": 1.0,
                    "duration_seconds": 7200,
                    "_required_type": "storage",
                },
            ],
            "traffic_multiplier": 1.0,
        },
    ],
    prerequisites=["database", "external_api"],
    estimated_duration="1hr",
    difficulty="expert",
    created_at=_CREATED,
    updated_at=_UPDATED,
    downloads=1240,
    rating=4.3,
    featured=False,
)


# ---------------------------------------------------------------------------
# 7. SOC2 Compliance Testing Suite
# ---------------------------------------------------------------------------
_compliance_soc2 = ScenarioPackage(
    id="compliance-validation-soc2",
    name="SOC2 Compliance Testing Suite",
    version="1.1.0",
    description=(
        "Scenarios to validate SOC2 Type II compliance: availability, "
        "processing integrity, confidentiality controls"
    ),
    author="ChaosProof Team",
    category="compliance",
    provider="generic",
    severity="high",
    tags=["compliance", "soc2", "audit", "availability", "integrity"],
    scenarios=[
        {
            "name": "Availability Control Test (CC7.1)",
            "description": "System availability under sustained degradation",
            "faults": [
                {
                    "target_component_id": "app-server",
                    "fault_type": "cpu_saturation",
                    "severity": 0.7,
                    "duration_seconds": 3600,
                    "_required_type": "app_server",
                },
            ],
            "traffic_multiplier": 2.0,
        },
        {
            "name": "Change Management Resilience (CC8.1)",
            "description": "Bad deployment causing service degradation",
            "faults": [
                {
                    "target_component_id": "app-server",
                    "fault_type": "component_down",
                    "severity": 0.8,
                    "duration_seconds": 600,
                    "_required_type": "app_server",
                },
            ],
            "traffic_multiplier": 1.0,
        },
        {
            "name": "Monitoring & Incident Response (CC7.2)",
            "description": "Cascading failure requiring rapid detection and response",
            "faults": [
                {
                    "target_component_id": "cache-primary",
                    "fault_type": "component_down",
                    "severity": 1.0,
                    "duration_seconds": 300,
                    "_required_type": "cache",
                },
                {
                    "target_component_id": "db-primary",
                    "fault_type": "connection_pool_exhaustion",
                    "severity": 0.8,
                    "duration_seconds": 600,
                    "_required_type": "database",
                },
            ],
            "traffic_multiplier": 1.5,
        },
    ],
    prerequisites=["app_server", "database"],
    estimated_duration="1hr",
    difficulty="advanced",
    created_at=_CREATED,
    updated_at=_UPDATED,
    downloads=980,
    rating=4.1,
    featured=False,
)


# ---------------------------------------------------------------------------
# 8. Microservices Resilience Patterns
# ---------------------------------------------------------------------------
_microservices_resilience = ScenarioPackage(
    id="microservices-resilience",
    name="Microservices Resilience Patterns",
    version="1.4.0",
    description=(
        "Test circuit breakers, bulkheads, retries, timeouts, "
        "and fallback patterns in microservice architectures"
    ),
    author="ChaosProof Team",
    category="infrastructure",
    provider="generic",
    severity="medium",
    tags=["microservices", "circuit-breaker", "bulkhead", "resilience", "retry"],
    scenarios=[
        {
            "name": "Circuit Breaker Trip",
            "description": "Downstream service fails causing circuit breaker to open",
            "faults": [
                {
                    "target_component_id": "downstream-svc",
                    "fault_type": "component_down",
                    "severity": 1.0,
                    "duration_seconds": 300,
                    "_required_type": "app_server",
                },
            ],
            "traffic_multiplier": 1.0,
        },
        {
            "name": "Retry Storm",
            "description": "Failed service causes retry storm amplifying traffic",
            "faults": [
                {
                    "target_component_id": "upstream-svc",
                    "fault_type": "latency_spike",
                    "severity": 0.5,
                    "duration_seconds": 600,
                    "_required_type": "app_server",
                    "parameters": {"latency_ms": 2000},
                },
            ],
            "traffic_multiplier": 4.0,
        },
        {
            "name": "Timeout Cascade",
            "description": "Slow service causes timeout cascade across service mesh",
            "faults": [
                {
                    "target_component_id": "slow-svc",
                    "fault_type": "latency_spike",
                    "severity": 0.8,
                    "duration_seconds": 900,
                    "_required_type": "app_server",
                    "parameters": {"latency_ms": 10000},
                },
                {
                    "target_component_id": "gateway",
                    "fault_type": "connection_pool_exhaustion",
                    "severity": 0.6,
                    "duration_seconds": 900,
                    "_required_type": "load_balancer",
                },
            ],
            "traffic_multiplier": 1.0,
        },
        {
            "name": "Bulkhead Overflow",
            "description": "One service consuming all shared resources, affecting others",
            "faults": [
                {
                    "target_component_id": "greedy-svc",
                    "fault_type": "memory_exhaustion",
                    "severity": 0.9,
                    "duration_seconds": 600,
                    "_required_type": "app_server",
                },
            ],
            "traffic_multiplier": 1.0,
        },
    ],
    prerequisites=["app_server", "load_balancer"],
    estimated_duration="30min",
    difficulty="intermediate",
    created_at=_CREATED,
    updated_at=_UPDATED,
    downloads=2650,
    rating=4.5,
    featured=True,
)


# ---------------------------------------------------------------------------
# 9. Data Pipeline Chaos Scenarios
# ---------------------------------------------------------------------------
_data_pipeline_chaos = ScenarioPackage(
    id="data-pipeline-chaos",
    name="Data Pipeline Chaos Scenarios",
    version="1.2.0",
    description=(
        "Kafka partition loss, Spark job failure, ETL pipeline corruption, "
        "data lake access denied"
    ),
    author="ChaosProof Team",
    category="infrastructure",
    provider="aws",
    severity="high",
    tags=["data", "pipeline", "kafka", "etl", "streaming", "spark"],
    scenarios=[
        {
            "name": "Kafka Partition Loss",
            "description": "Kafka broker failure causing partition leader re-election",
            "faults": [
                {
                    "target_component_id": "kafka-broker",
                    "fault_type": "component_down",
                    "severity": 1.0,
                    "duration_seconds": 300,
                    "_required_type": "queue",
                },
            ],
            "traffic_multiplier": 1.0,
        },
        {
            "name": "ETL Pipeline Failure",
            "description": "ETL job fails mid-execution leaving partial data",
            "faults": [
                {
                    "target_component_id": "etl-worker",
                    "fault_type": "component_down",
                    "severity": 0.8,
                    "duration_seconds": 1800,
                    "_required_type": "app_server",
                },
                {
                    "target_component_id": "staging-db",
                    "fault_type": "disk_full",
                    "severity": 0.7,
                    "duration_seconds": 1800,
                    "_required_type": "database",
                },
            ],
            "traffic_multiplier": 1.0,
        },
        {
            "name": "Data Lake Access Denied",
            "description": "S3/storage IAM policy change blocks data access",
            "faults": [
                {
                    "target_component_id": "data-lake",
                    "fault_type": "component_down",
                    "severity": 0.9,
                    "duration_seconds": 600,
                    "_required_type": "storage",
                    "parameters": {"reason": "iam_policy_change"},
                },
            ],
            "traffic_multiplier": 1.0,
        },
    ],
    prerequisites=["queue", "database", "storage"],
    estimated_duration="30min",
    difficulty="advanced",
    created_at=_CREATED,
    updated_at=_UPDATED,
    downloads=1580,
    rating=4.2,
    featured=False,
)


# ---------------------------------------------------------------------------
# 10. CDN & Edge Failure Scenarios
# ---------------------------------------------------------------------------
_cdn_edge_failures = ScenarioPackage(
    id="cdn-edge-failures",
    name="CDN & Edge Failure Scenarios",
    version="1.1.0",
    description=(
        "CDN cache invalidation, origin failover, edge compute failure, "
        "SSL renewal failure"
    ),
    author="ChaosProof Team",
    category="infrastructure",
    provider="generic",
    severity="medium",
    tags=["cdn", "edge", "cache", "cloudfront", "ssl", "origin"],
    scenarios=[
        {
            "name": "CDN Origin Failover",
            "description": "CDN origin server becomes unreachable forcing failover",
            "faults": [
                {
                    "target_component_id": "origin-server",
                    "fault_type": "component_down",
                    "severity": 1.0,
                    "duration_seconds": 300,
                    "_required_type": "web_server",
                },
            ],
            "traffic_multiplier": 1.0,
        },
        {
            "name": "Cache Invalidation Storm",
            "description": "Mass cache invalidation causing thundering herd to origin",
            "faults": [
                {
                    "target_component_id": "cache-cdn",
                    "fault_type": "component_down",
                    "severity": 0.9,
                    "duration_seconds": 120,
                    "_required_type": "cache",
                },
            ],
            "traffic_multiplier": 8.0,
        },
        {
            "name": "Edge Compute Failure",
            "description": "Edge function runtime failure at CDN edge locations",
            "faults": [
                {
                    "target_component_id": "edge-function",
                    "fault_type": "component_down",
                    "severity": 0.7,
                    "duration_seconds": 600,
                    "_required_type": "app_server",
                },
            ],
            "traffic_multiplier": 1.0,
        },
    ],
    prerequisites=["web_server", "cache"],
    estimated_duration="30min",
    difficulty="intermediate",
    created_at=_CREATED,
    updated_at=_UPDATED,
    downloads=1120,
    rating=4.0,
    featured=False,
)


# ---------------------------------------------------------------------------
# 11. Third-Party Outage Simulator
# ---------------------------------------------------------------------------
_third_party_outage = ScenarioPackage(
    id="third-party-outage-sim",
    name="Third-Party Outage Simulator",
    version="1.3.0",
    description=(
        "Simulate outages of common third-party services: Stripe, Auth0, "
        "Twilio, SendGrid, Datadog"
    ),
    author="ChaosProof Team",
    category="infrastructure",
    provider="generic",
    severity="high",
    tags=["third-party", "stripe", "auth0", "twilio", "sendgrid", "outage"],
    scenarios=[
        {
            "name": "Payment Provider Outage (Stripe)",
            "description": "Payment processing API becomes unavailable",
            "faults": [
                {
                    "target_component_id": "stripe-api",
                    "fault_type": "component_down",
                    "severity": 1.0,
                    "duration_seconds": 1800,
                    "_required_type": "external_api",
                },
            ],
            "traffic_multiplier": 1.0,
        },
        {
            "name": "Authentication Provider Down (Auth0)",
            "description": "SSO/authentication provider unreachable",
            "faults": [
                {
                    "target_component_id": "auth0-api",
                    "fault_type": "component_down",
                    "severity": 1.0,
                    "duration_seconds": 3600,
                    "_required_type": "external_api",
                },
            ],
            "traffic_multiplier": 1.0,
        },
        {
            "name": "Notification Service Degradation (Twilio)",
            "description": "SMS/notification API returning 503 errors intermittently",
            "faults": [
                {
                    "target_component_id": "twilio-api",
                    "fault_type": "latency_spike",
                    "severity": 0.6,
                    "duration_seconds": 7200,
                    "_required_type": "external_api",
                    "parameters": {"error_rate": 0.3},
                },
            ],
            "traffic_multiplier": 1.0,
        },
        {
            "name": "Monitoring Blind Spot (Datadog)",
            "description": "Observability platform goes down during an incident",
            "faults": [
                {
                    "target_component_id": "datadog-agent",
                    "fault_type": "component_down",
                    "severity": 0.5,
                    "duration_seconds": 3600,
                    "_required_type": "external_api",
                },
            ],
            "traffic_multiplier": 1.0,
        },
    ],
    prerequisites=["external_api"],
    estimated_duration="30min",
    difficulty="beginner",
    created_at=_CREATED,
    updated_at=_UPDATED,
    downloads=2340,
    rating=4.6,
    featured=False,
)


# ---------------------------------------------------------------------------
# 12. Load & Performance Chaos
# ---------------------------------------------------------------------------
_load_testing_chaos = ScenarioPackage(
    id="load-testing-chaos",
    name="Load & Performance Chaos",
    version="1.5.0",
    description=(
        "Traffic spike, connection pool exhaustion, memory leak, "
        "CPU spike, disk IO saturation"
    ),
    author="ChaosProof Team",
    category="performance",
    provider="generic",
    severity="high",
    tags=["load", "performance", "traffic", "memory-leak", "cpu", "io"],
    scenarios=[
        {
            "name": "10x Traffic Spike",
            "description": "Sudden 10x traffic increase simulating viral event",
            "faults": [
                {
                    "target_component_id": "lb-primary",
                    "fault_type": "cpu_saturation",
                    "severity": 0.5,
                    "duration_seconds": 600,
                    "_required_type": "load_balancer",
                },
            ],
            "traffic_multiplier": 10.0,
        },
        {
            "name": "Memory Leak Simulation",
            "description": "Gradual memory leak reaching OOM threshold",
            "faults": [
                {
                    "target_component_id": "app-server",
                    "fault_type": "memory_exhaustion",
                    "severity": 0.9,
                    "duration_seconds": 3600,
                    "_required_type": "app_server",
                    "parameters": {"leak_rate_mb_per_min": 50},
                },
            ],
            "traffic_multiplier": 1.0,
        },
        {
            "name": "CPU Spike Under Load",
            "description": "CPU spike during peak traffic period",
            "faults": [
                {
                    "target_component_id": "app-server",
                    "fault_type": "cpu_saturation",
                    "severity": 0.95,
                    "duration_seconds": 300,
                    "_required_type": "app_server",
                },
            ],
            "traffic_multiplier": 3.0,
        },
        {
            "name": "Disk IO Saturation",
            "description": "Disk IO bottleneck from write-heavy workload",
            "faults": [
                {
                    "target_component_id": "db-primary",
                    "fault_type": "disk_full",
                    "severity": 0.7,
                    "duration_seconds": 1200,
                    "_required_type": "database",
                },
            ],
            "traffic_multiplier": 2.0,
        },
    ],
    prerequisites=["app_server", "load_balancer"],
    estimated_duration="30min",
    difficulty="intermediate",
    created_at=_CREATED,
    updated_at=_UPDATED,
    downloads=3780,
    rating=4.4,
    featured=False,
)


# ---------------------------------------------------------------------------
# 13. Deployment Gone Wrong Scenarios
# ---------------------------------------------------------------------------
_deployment_chaos = ScenarioPackage(
    id="deployment-chaos",
    name="Deployment Gone Wrong Scenarios",
    version="1.2.0",
    description=(
        "Bad deployment rollback, canary failure, blue-green switch failure, "
        "config drift"
    ),
    author="ChaosProof Team",
    category="infrastructure",
    provider="generic",
    severity="high",
    tags=["deployment", "rollback", "canary", "blue-green", "config-drift"],
    scenarios=[
        {
            "name": "Bad Deployment Rollback",
            "description": "Deployment causes crash loop, requiring rollback",
            "faults": [
                {
                    "target_component_id": "app-server-v2",
                    "fault_type": "component_down",
                    "severity": 1.0,
                    "duration_seconds": 300,
                    "_required_type": "app_server",
                },
            ],
            "traffic_multiplier": 1.0,
        },
        {
            "name": "Canary Failure Undetected",
            "description": "Canary deployment with subtle error increase not caught by metrics",
            "faults": [
                {
                    "target_component_id": "app-canary",
                    "fault_type": "latency_spike",
                    "severity": 0.3,
                    "duration_seconds": 1800,
                    "_required_type": "app_server",
                    "parameters": {"error_rate": 0.05},
                },
            ],
            "traffic_multiplier": 1.0,
        },
        {
            "name": "Blue-Green Switch Failure",
            "description": "Load balancer fails to switch traffic from blue to green",
            "faults": [
                {
                    "target_component_id": "lb-primary",
                    "fault_type": "component_down",
                    "severity": 0.8,
                    "duration_seconds": 120,
                    "_required_type": "load_balancer",
                },
            ],
            "traffic_multiplier": 1.0,
        },
        {
            "name": "Configuration Drift",
            "description": "Environment config mismatch between staging and production",
            "faults": [
                {
                    "target_component_id": "app-server",
                    "fault_type": "component_down",
                    "severity": 0.6,
                    "duration_seconds": 600,
                    "_required_type": "app_server",
                    "parameters": {"reason": "config_mismatch"},
                },
                {
                    "target_component_id": "cache-primary",
                    "fault_type": "component_down",
                    "severity": 0.4,
                    "duration_seconds": 600,
                    "_required_type": "cache",
                    "parameters": {"reason": "missing_env_var"},
                },
            ],
            "traffic_multiplier": 1.0,
        },
    ],
    prerequisites=["app_server", "load_balancer"],
    estimated_duration="30min",
    difficulty="intermediate",
    created_at=_CREATED,
    updated_at=_UPDATED,
    downloads=2100,
    rating=4.3,
    featured=False,
)


# ---------------------------------------------------------------------------
# 14. Observability System Failures
# ---------------------------------------------------------------------------
_observability_failure = ScenarioPackage(
    id="observability-failure",
    name="Observability System Failures",
    version="1.0.0",
    description=(
        "What happens when your monitoring goes down? Prometheus failure, "
        "log pipeline break, alert fatigue simulation"
    ),
    author="ChaosProof Team",
    category="infrastructure",
    provider="generic",
    severity="medium",
    tags=["observability", "monitoring", "prometheus", "logging", "alerts"],
    scenarios=[
        {
            "name": "Prometheus Server Down",
            "description": "Monitoring system fails during an active incident",
            "faults": [
                {
                    "target_component_id": "prometheus",
                    "fault_type": "component_down",
                    "severity": 0.8,
                    "duration_seconds": 1800,
                    "_required_type": "app_server",
                },
            ],
            "traffic_multiplier": 1.0,
        },
        {
            "name": "Log Pipeline Break",
            "description": "ELK/Loki log pipeline congested, logs being dropped",
            "faults": [
                {
                    "target_component_id": "log-aggregator",
                    "fault_type": "disk_full",
                    "severity": 0.7,
                    "duration_seconds": 3600,
                    "_required_type": "storage",
                },
            ],
            "traffic_multiplier": 1.0,
        },
        {
            "name": "Alert Fatigue Simulation",
            "description": "High volume of non-critical alerts masking real issues",
            "faults": [
                {
                    "target_component_id": "alertmanager",
                    "fault_type": "cpu_saturation",
                    "severity": 0.5,
                    "duration_seconds": 7200,
                    "_required_type": "app_server",
                    "parameters": {"alert_count": 500},
                },
            ],
            "traffic_multiplier": 1.0,
        },
    ],
    prerequisites=["app_server"],
    estimated_duration="30min",
    difficulty="advanced",
    created_at=_CREATED,
    updated_at=_UPDATED,
    downloads=890,
    rating=4.0,
    featured=False,
)


# ---------------------------------------------------------------------------
# 15. GameDay Starter Kit
# ---------------------------------------------------------------------------
_gameday_starter_kit = ScenarioPackage(
    id="gameday-starter-kit",
    name="GameDay Starter Kit",
    version="2.0.0",
    description=(
        "Pre-built GameDay exercise packages for teams new to chaos engineering. "
        "Gentle, well-documented scenarios with clear rollback procedures"
    ),
    author="ChaosProof Team",
    category="infrastructure",
    provider="generic",
    severity="low",
    tags=["gameday", "starter", "beginner", "workshop", "training"],
    scenarios=[
        {
            "name": "Single Server Failure",
            "description": "Basic single-server failure to verify failover works",
            "faults": [
                {
                    "target_component_id": "app-server-1",
                    "fault_type": "component_down",
                    "severity": 1.0,
                    "duration_seconds": 120,
                    "_required_type": "app_server",
                },
            ],
            "traffic_multiplier": 1.0,
        },
        {
            "name": "Cache Miss Storm",
            "description": "Cache goes down, all requests hit the database",
            "faults": [
                {
                    "target_component_id": "cache-primary",
                    "fault_type": "component_down",
                    "severity": 1.0,
                    "duration_seconds": 300,
                    "_required_type": "cache",
                },
            ],
            "traffic_multiplier": 1.5,
        },
        {
            "name": "Gradual Latency Increase",
            "description": "Slowly increasing latency to test monitoring alerting thresholds",
            "faults": [
                {
                    "target_component_id": "app-server",
                    "fault_type": "latency_spike",
                    "severity": 0.3,
                    "duration_seconds": 900,
                    "_required_type": "app_server",
                    "parameters": {"latency_ms": 200},
                },
            ],
            "traffic_multiplier": 1.0,
        },
        {
            "name": "External Dependency Timeout",
            "description": "External API starts timing out - does the app degrade gracefully?",
            "faults": [
                {
                    "target_component_id": "external-api",
                    "fault_type": "latency_spike",
                    "severity": 0.5,
                    "duration_seconds": 600,
                    "_required_type": "external_api",
                    "parameters": {"latency_ms": 30000},
                },
            ],
            "traffic_multiplier": 1.0,
        },
        {
            "name": "Double Trouble",
            "description": "Two simultaneous failures - cache down + traffic spike",
            "faults": [
                {
                    "target_component_id": "cache-primary",
                    "fault_type": "component_down",
                    "severity": 1.0,
                    "duration_seconds": 300,
                    "_required_type": "cache",
                },
            ],
            "traffic_multiplier": 3.0,
        },
    ],
    prerequisites=["app_server", "cache"],
    estimated_duration="1hr",
    difficulty="beginner",
    created_at=_CREATED,
    updated_at=_UPDATED,
    downloads=5120,
    rating=4.9,
    featured=True,
)


# ---------------------------------------------------------------------------
# Public list
# ---------------------------------------------------------------------------

BUILTIN_PACKAGES: list[ScenarioPackage] = [
    _aws_region_failover,
    _aws_database_chaos,
    _kubernetes_pod_disruption,
    _security_attack_simulation,
    _network_chaos_pack,
    _compliance_dora,
    _compliance_soc2,
    _microservices_resilience,
    _data_pipeline_chaos,
    _cdn_edge_failures,
    _third_party_outage,
    _load_testing_chaos,
    _deployment_chaos,
    _observability_failure,
    _gameday_starter_kit,
]
