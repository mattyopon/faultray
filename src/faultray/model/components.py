"""Infrastructure component models."""

from __future__ import annotations

from enum import Enum
from pydantic import BaseModel, Field, field_validator

SCHEMA_VERSION = "4.0"


class ComponentType(str, Enum):
    LOAD_BALANCER = "load_balancer"
    WEB_SERVER = "web_server"
    APP_SERVER = "app_server"
    DATABASE = "database"
    CACHE = "cache"
    QUEUE = "queue"
    STORAGE = "storage"
    DNS = "dns"
    EXTERNAL_API = "external_api"
    CUSTOM = "custom"
    AI_AGENT = "ai_agent"
    LLM_ENDPOINT = "llm_endpoint"
    TOOL_SERVICE = "tool_service"
    AGENT_ORCHESTRATOR = "agent_orchestrator"


class ResourceMetrics(BaseModel):
    """Current resource usage metrics for a component."""

    cpu_percent: float = 0.0
    memory_percent: float = 0.0
    memory_used_mb: float = 0.0
    memory_total_mb: float = 0.0
    disk_percent: float = 0.0
    disk_used_gb: float = 0.0
    disk_total_gb: float = 0.0
    network_connections: int = 0
    open_files: int = 0


class NetworkProfile(BaseModel):
    """Network characteristics for request-level availability modeling."""

    rtt_ms: float = 1.0  # Round-trip time in milliseconds
    packet_loss_rate: float = 0.0001  # Baseline packet loss (0.01%)
    jitter_ms: float = 0.5  # Network jitter (stddev)
    dns_resolution_ms: float = 5.0  # DNS lookup time
    tls_handshake_ms: float = 10.0  # TLS setup time


class RuntimeJitter(BaseModel):
    """Application-level jitter sources."""

    gc_pause_ms: float = 0.0  # Average GC pause (0 = no GC, e.g. Go/Rust)
    gc_pause_frequency: float = 0.0  # GC pauses per second
    scheduling_jitter_ms: float = 0.1  # OS kernel scheduling jitter


class Capacity(BaseModel):
    """Capacity limits and thresholds for a component."""

    max_connections: int = 1000
    max_rps: int = 5000
    connection_pool_size: int = 100
    max_memory_mb: float = 8192
    max_disk_gb: float = 100
    timeout_seconds: float = 30.0
    retry_multiplier: float = 3.0


class AutoScalingConfig(BaseModel):
    """HPA/KEDA autoscaling configuration."""

    enabled: bool = False
    min_replicas: int = 1
    max_replicas: int = 1
    scale_up_threshold: float = 70.0  # CPU% to trigger scale up
    scale_down_threshold: float = 30.0  # CPU% to trigger scale down
    scale_up_delay_seconds: int = 15  # time to provision new replica
    scale_down_delay_seconds: int = 300  # cooldown before scale down
    scale_up_step: int = 2  # replicas to add per step


class FailoverConfig(BaseModel):
    """Failover/promotion configuration."""

    enabled: bool = False
    promotion_time_seconds: float = 30.0  # time for replica to promote to primary
    health_check_interval_seconds: float = 10.0
    failover_threshold: int = 3  # consecutive failures before failover


class CircuitBreakerConfig(BaseModel):
    """Circuit breaker configuration for a dependency edge."""

    enabled: bool = False
    failure_threshold: int = 5  # consecutive failures to trip OPEN
    recovery_timeout_seconds: float = 60.0  # stay OPEN before HALF_OPEN
    half_open_max_requests: int = 3  # requests allowed in HALF_OPEN
    success_threshold: int = 2  # successes in HALF_OPEN to close


class RetryStrategy(BaseModel):
    """Adaptive retry with exponential backoff + jitter."""

    enabled: bool = False
    max_retries: int = 3
    initial_delay_ms: float = 100.0
    max_delay_ms: float = 30000.0
    multiplier: float = 2.0  # delay = initial_delay * multiplier^attempt
    jitter: bool = True  # add random jitter to prevent thundering herd
    retry_budget_per_second: float = 0.0  # 0 = unlimited; >0 = max retries/sec


class CacheWarmingConfig(BaseModel):
    """Cache warming behaviour after recovery from DOWN."""

    enabled: bool = False
    initial_hit_ratio: float = 0.0  # hit ratio right after recovery
    warm_duration_seconds: int = 300  # time to reach full hit ratio
    warming_curve: str = "linear"  # linear, exponential


class SingleflightConfig(BaseModel):
    """Singleflight / request coalescing to deduplicate concurrent requests."""

    enabled: bool = False
    coalesce_ratio: float = 0.8  # fraction of duplicate requests coalesced (0-1)


class RegionConfig(BaseModel):
    """Multi-region / DR configuration for a component."""

    region: str = ""
    availability_zone: str = ""
    is_primary: bool = True
    dr_target_region: str = ""
    rpo_seconds: int = 0
    rto_seconds: int = 0


class ExternalSLAConfig(BaseModel):
    """External dependency SLA configuration.

    Used for Layer 5 (External SLA Cascading) in the 5-Layer Availability Model.
    When a component of type ``external_api`` or any component with an explicit
    ``external_sla`` config is present, its provider SLA is multiplied into the
    external-availability layer.
    """

    provider_sla: float = 99.9  # percentage, e.g., 99.9 = three nines


class SLOTarget(BaseModel):
    """Service Level Objective definition."""

    name: str = ""
    metric: str = "availability"  # availability | latency_p99 | error_rate
    target: float = 99.9
    unit: str = "percent"  # percent | ms | ratio
    window_days: int = 30


class CostProfile(BaseModel):
    """Cost characteristics for business impact analysis."""

    hourly_infra_cost: float = 0.0
    revenue_per_minute: float = 0.0
    sla_credit_percent: float = 0.0
    recovery_engineer_cost: float = 100.0

    # Extended cost fields for executive summary ROI analysis
    monthly_contract_value: float = 0.0
    customer_ltv: float = 0.0
    churn_rate_per_hour_outage: float = 0.001
    recovery_team_size: int = 0  # 0 = use engine default
    data_loss_cost_per_gb: float = 0.0


class ComplianceTags(BaseModel):
    """Compliance and data classification tags for regulatory assessment."""

    data_classification: str = "internal"  # public/internal/confidential/restricted
    pci_scope: bool = False
    contains_pii: bool = False
    contains_phi: bool = False
    audit_logging: bool = False
    change_management: bool = False


class OperationalTeamConfig(BaseModel):
    """Team operational readiness configuration."""

    team_size: int = 3
    oncall_coverage_hours: float = 24.0
    timezone_coverage: int = 1
    mean_acknowledge_time_minutes: float = 5.0
    mean_diagnosis_time_minutes: float = 15.0
    runbook_coverage_percent: float = 50.0
    automation_percent: float = 20.0


class SecurityProfile(BaseModel):
    """Security configuration for blast radius and attack resilience analysis."""

    encryption_at_rest: bool = False
    encryption_in_transit: bool = False
    waf_protected: bool = False
    rate_limiting: bool = False
    auth_required: bool = False
    network_segmented: bool = False
    backup_enabled: bool = False
    backup_frequency_hours: float = 24.0
    patch_sla_hours: float = 72.0
    log_enabled: bool = False
    ids_monitored: bool = False


class DegradationConfig(BaseModel):
    """Gradual degradation model for a component."""

    memory_leak_mb_per_hour: float = 0.0
    disk_fill_gb_per_hour: float = 0.0
    connection_leak_per_hour: float = 0.0


class OperationalProfile(BaseModel):
    """Operational characteristics of a component."""

    mtbf_hours: float = 0.0
    mttr_minutes: float = 30.0
    deploy_downtime_seconds: float = 30.0
    maintenance_downtime_minutes: float = 60.0
    degradation: DegradationConfig = Field(default_factory=DegradationConfig)


class HealthStatus(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    OVERLOADED = "overloaded"
    DOWN = "down"


class Component(BaseModel):
    """A single infrastructure component."""

    id: str
    name: str
    type: ComponentType
    host: str = ""
    port: int = 0
    replicas: int = 1
    metrics: ResourceMetrics = Field(default_factory=ResourceMetrics)
    capacity: Capacity = Field(default_factory=Capacity)
    health: HealthStatus = HealthStatus.HEALTHY
    autoscaling: AutoScalingConfig = Field(default_factory=AutoScalingConfig)
    failover: FailoverConfig = Field(default_factory=FailoverConfig)
    cache_warming: CacheWarmingConfig = Field(default_factory=CacheWarmingConfig)
    singleflight: SingleflightConfig = Field(default_factory=SingleflightConfig)
    slo_targets: list[SLOTarget] = Field(default_factory=list)
    external_sla: ExternalSLAConfig | None = None
    cost_profile: CostProfile = Field(default_factory=CostProfile)
    operational_profile: OperationalProfile = Field(default_factory=OperationalProfile)
    region: RegionConfig = Field(default_factory=RegionConfig)
    network: NetworkProfile = Field(default_factory=NetworkProfile)
    runtime_jitter: RuntimeJitter = Field(default_factory=RuntimeJitter)
    security: SecurityProfile = Field(default_factory=SecurityProfile)
    compliance_tags: ComplianceTags = Field(default_factory=ComplianceTags)
    team: OperationalTeamConfig = Field(default_factory=OperationalTeamConfig)
    parameters: dict[str, float | int | str] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)

    @field_validator('replicas')
    @classmethod
    def validate_replicas(cls, v):
        if v < 1:
            raise ValueError(f"replicas must be >= 1, got {v}")
        return v

    def utilization(self) -> float:
        """Calculate overall utilization as a percentage (0-100)."""
        factors = []
        if self.capacity.max_connections > 0:
            factors.append(
                self.metrics.network_connections / self.capacity.max_connections * 100
            )
        if self.metrics.cpu_percent > 0:
            factors.append(self.metrics.cpu_percent)
        if self.metrics.memory_percent > 0:
            factors.append(self.metrics.memory_percent)
        if self.metrics.disk_percent > 0:
            factors.append(self.metrics.disk_percent)
        return max(factors) if factors else 0.0

    def effective_capacity_at_replicas(self, replica_count: int) -> float:
        """Calculate effective capacity multiplier for given replica count vs base."""
        if self.replicas <= 0:
            return 0.0
        return replica_count / self.replicas


class Dependency(BaseModel):
    """A dependency between two components."""

    source_id: str
    target_id: str
    dependency_type: str = "requires"  # requires, optional, async
    protocol: str = ""  # tcp, http, grpc, etc.
    port: int = 0
    latency_ms: float = 0.0
    weight: float = 1.0  # how critical this dependency is (0.0-1.0)
    circuit_breaker: CircuitBreakerConfig = Field(default_factory=CircuitBreakerConfig)
    retry_strategy: RetryStrategy = Field(default_factory=RetryStrategy)
