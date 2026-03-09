"""Infrastructure component models."""

from __future__ import annotations

from enum import Enum
from pydantic import BaseModel, Field


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


class Capacity(BaseModel):
    """Capacity limits and thresholds for a component."""

    max_connections: int = 1000
    max_rps: int = 5000
    connection_pool_size: int = 100
    max_memory_mb: float = 8192
    max_disk_gb: float = 100
    timeout_seconds: float = 30.0
    retry_multiplier: float = 3.0


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
    parameters: dict[str, float | int | str] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)

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


class Dependency(BaseModel):
    """A dependency between two components."""

    source_id: str
    target_id: str
    dependency_type: str = "requires"  # requires, optional, async
    protocol: str = ""  # tcp, http, grpc, etc.
    port: int = 0
    latency_ms: float = 0.0
    weight: float = 1.0  # how critical this dependency is (0.0-1.0)
