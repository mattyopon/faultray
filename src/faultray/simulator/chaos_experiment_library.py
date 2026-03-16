"""Chaos Experiment Template Library.

Provides a curated library of chaos experiment templates mapped to common
failure patterns.  Each template encodes a hypothesis, steady-state
definition, injection method, expected outcome, and rollback steps so that
operators can execute well-understood chaos experiments against their
infrastructure with minimal guesswork.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field

from faultray.model.components import ComponentType, HealthStatus
from faultray.model.graph import InfraGraph


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class ExperimentCategory(str, Enum):
    """Broad categories of chaos experiment."""

    AVAILABILITY = "availability"
    LATENCY = "latency"
    DATA = "data"
    SECURITY = "security"
    CAPACITY = "capacity"
    DEPENDENCY = "dependency"
    STATE = "state"
    CONFIGURATION = "configuration"


class Difficulty(str, Enum):
    """Difficulty / risk level for running an experiment."""

    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"
    EXPERT = "expert"


# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------


class ExperimentTemplate(BaseModel):
    """A reusable chaos experiment template."""

    id: str
    name: str
    category: ExperimentCategory
    difficulty: Difficulty
    description: str
    hypothesis: str
    steady_state: str
    injection_method: str
    expected_outcome: str
    rollback_steps: list[str]
    applicable_component_types: list[str]
    estimated_duration_minutes: int
    blast_radius: str
    prerequisites: list[str]
    tags: list[str]


class ExperimentRecommendation(BaseModel):
    """A recommended experiment for a specific component."""

    template: ExperimentTemplate
    target_component: str
    relevance_score: float = Field(default=0.0, ge=0.0, le=1.0)
    reason: str
    priority: str


class ExperimentPlanEntry(BaseModel):
    """An entry inside an ordered experiment plan."""

    order: int
    template: ExperimentTemplate
    target_component: str
    reason: str
    priority: str


class ExperimentPlan(BaseModel):
    """An ordered plan of experiments to execute."""

    entries: list[ExperimentPlanEntry] = Field(default_factory=list)
    total_estimated_minutes: int = 0
    categories_covered: list[str] = Field(default_factory=list)
    components_covered: list[str] = Field(default_factory=list)


class PrerequisiteCheck(BaseModel):
    """Result of checking whether prerequisites are met for a template."""

    template_id: str
    satisfied: bool = True
    met: list[str] = Field(default_factory=list)
    unmet: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class CoverageReport(BaseModel):
    """Coverage report showing how much of the infrastructure has been tested."""

    total_components: int = 0
    covered_components: int = 0
    coverage_percent: float = 0.0
    categories_tested: list[str] = Field(default_factory=list)
    categories_untested: list[str] = Field(default_factory=list)
    component_coverage: dict[str, list[str]] = Field(default_factory=dict)
    recommendations: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Prerequisite helpers
# ---------------------------------------------------------------------------

_PREREQUISITE_CHECKERS: dict[str, str] = {
    "monitoring": "monitoring",
    "replicas > 1": "replicas",
    "circuit breaker enabled": "circuit_breaker",
    "failover configured": "failover",
    "autoscaling enabled": "autoscaling",
    "backup enabled": "backup",
    "health check configured": "health_check",
    "load balancer in path": "load_balancer",
    "observability enabled": "observability",
    "rate limiting enabled": "rate_limiting",
    "encryption at rest": "encryption_at_rest",
    "encryption in transit": "encryption_in_transit",
    "network segmentation": "network_segmented",
    "rollback procedure documented": "rollback_doc",
}


def _check_prerequisite(prereq: str, graph: InfraGraph, component_id: str | None) -> bool:
    """Return True if the named prerequisite is satisfied."""
    prereq_lower = prereq.lower()

    if "monitoring" in prereq_lower or "observability" in prereq_lower:
        # Satisfied if at least one component has health != DOWN
        return any(
            c.health != HealthStatus.DOWN for c in graph.components.values()
        )

    if "replicas" in prereq_lower:
        if component_id and component_id in graph.components:
            return graph.components[component_id].replicas > 1
        return any(c.replicas > 1 for c in graph.components.values())

    if "circuit breaker" in prereq_lower:
        edges = graph.all_dependency_edges()
        return any(getattr(e, "circuit_breaker", None) and e.circuit_breaker.enabled for e in edges)

    if "failover" in prereq_lower:
        return any(c.failover.enabled for c in graph.components.values())

    if "autoscaling" in prereq_lower:
        return any(c.autoscaling.enabled for c in graph.components.values())

    if "backup" in prereq_lower:
        return any(c.security.backup_enabled for c in graph.components.values())

    if "health check" in prereq_lower:
        return len(graph.components) > 0

    if "load balancer" in prereq_lower:
        return any(
            c.type == ComponentType.LOAD_BALANCER for c in graph.components.values()
        )

    if "rate limiting" in prereq_lower:
        return any(c.security.rate_limiting for c in graph.components.values())

    if "encryption at rest" in prereq_lower:
        return any(c.security.encryption_at_rest for c in graph.components.values())

    if "encryption in transit" in prereq_lower:
        return any(c.security.encryption_in_transit for c in graph.components.values())

    if "network segmentation" in prereq_lower or "network segmented" in prereq_lower:
        return any(c.security.network_segmented for c in graph.components.values())

    if "rollback" in prereq_lower:
        # Always considered met — documentation is external
        return True

    # Unknown prerequisite — optimistically pass
    return True


# ---------------------------------------------------------------------------
# Built-in template library (20+ templates across all 8 categories)
# ---------------------------------------------------------------------------

_BUILTIN_TEMPLATES: list[ExperimentTemplate] = [
    # ── AVAILABILITY (3) ──
    ExperimentTemplate(
        id="avail-001",
        name="Single Node Failure",
        category=ExperimentCategory.AVAILABILITY,
        difficulty=Difficulty.BEGINNER,
        description="Terminate a single instance and observe recovery behaviour.",
        hypothesis="The system continues serving traffic with minimal impact when one node goes down.",
        steady_state="All health checks pass and error rate < 0.1%.",
        injection_method="Kill one process or terminate one VM instance.",
        expected_outcome="Traffic is rerouted within health-check interval; no user-visible errors.",
        rollback_steps=["Restart the terminated instance", "Verify health checks pass"],
        applicable_component_types=["app_server", "web_server", "cache", "queue"],
        estimated_duration_minutes=15,
        blast_radius="single node",
        prerequisites=["monitoring", "replicas > 1"],
        tags=["availability", "node-failure", "beginner"],
    ),
    ExperimentTemplate(
        id="avail-002",
        name="Multi-AZ Failover",
        category=ExperimentCategory.AVAILABILITY,
        difficulty=Difficulty.ADVANCED,
        description="Simulate a full availability-zone outage.",
        hypothesis="The system fails over to the secondary AZ without data loss.",
        steady_state="All endpoints return 200 and latency < SLO target.",
        injection_method="Block all network traffic to/from one AZ using iptables or security group rules.",
        expected_outcome="Failover completes within RTO; RPO is met.",
        rollback_steps=["Restore network connectivity to the AZ", "Re-sync data if needed", "Verify replication status"],
        applicable_component_types=["app_server", "database", "cache", "load_balancer"],
        estimated_duration_minutes=45,
        blast_radius="availability zone",
        prerequisites=["failover configured", "monitoring", "replicas > 1"],
        tags=["availability", "failover", "multi-az", "advanced"],
    ),
    ExperimentTemplate(
        id="avail-003",
        name="Load Balancer Health Check Failure",
        category=ExperimentCategory.AVAILABILITY,
        difficulty=Difficulty.BEGINNER,
        description="Make one backend fail health checks to verify LB removes it from rotation.",
        hypothesis="The load balancer detects the unhealthy backend and stops routing traffic to it.",
        steady_state="All backends are in-rotation and serving traffic.",
        injection_method="Return 503 from the health check endpoint of one backend.",
        expected_outcome="LB removes backend from pool; traffic shifts to healthy nodes; no 5xx to clients.",
        rollback_steps=["Restore the health check endpoint", "Verify backend re-enters rotation"],
        applicable_component_types=["load_balancer", "app_server", "web_server"],
        estimated_duration_minutes=10,
        blast_radius="single node",
        prerequisites=["load balancer in path", "monitoring"],
        tags=["availability", "health-check", "load-balancer", "beginner"],
    ),

    # ── LATENCY (3) ──
    ExperimentTemplate(
        id="lat-001",
        name="Network Latency Injection",
        category=ExperimentCategory.LATENCY,
        difficulty=Difficulty.INTERMEDIATE,
        description="Add artificial latency to network calls between services.",
        hypothesis="The system gracefully degrades under increased latency and does not cascade timeouts.",
        steady_state="P99 latency < 200ms, error rate < 0.1%.",
        injection_method="Use tc/netem to add 200ms latency on the target interface.",
        expected_outcome="Timeouts trigger circuit breakers; degraded but functional responses.",
        rollback_steps=["Remove tc/netem rules", "Verify latency returns to baseline"],
        applicable_component_types=["app_server", "web_server", "database", "cache", "external_api"],
        estimated_duration_minutes=20,
        blast_radius="service-to-service",
        prerequisites=["monitoring", "circuit breaker enabled"],
        tags=["latency", "network", "intermediate"],
    ),
    ExperimentTemplate(
        id="lat-002",
        name="Database Slow Query",
        category=ExperimentCategory.LATENCY,
        difficulty=Difficulty.INTERMEDIATE,
        description="Introduce artificial delay in database queries.",
        hypothesis="The application handles slow queries without thread/connection pool exhaustion.",
        steady_state="Query p99 < 50ms, connection pool usage < 60%.",
        injection_method="Add pg_sleep or SLEEP() to critical queries via proxy or instrumentation.",
        expected_outcome="Connection pool is not exhausted; timeouts protect upstream services.",
        rollback_steps=["Remove query delay instrumentation", "Reset connection pools"],
        applicable_component_types=["database"],
        estimated_duration_minutes=25,
        blast_radius="database clients",
        prerequisites=["monitoring", "health check configured"],
        tags=["latency", "database", "slow-query", "intermediate"],
    ),
    ExperimentTemplate(
        id="lat-003",
        name="DNS Resolution Delay",
        category=ExperimentCategory.LATENCY,
        difficulty=Difficulty.ADVANCED,
        description="Introduce delay in DNS resolution to simulate DNS infrastructure issues.",
        hypothesis="Services handle DNS delays via caching or retry without cascading failures.",
        steady_state="DNS resolution < 10ms, all services operational.",
        injection_method="Add latency to DNS resolver responses using a proxy or iptables delay.",
        expected_outcome="Services use cached DNS or retry; no hard failures from DNS delay alone.",
        rollback_steps=["Remove DNS delay rules", "Flush DNS caches if needed"],
        applicable_component_types=["dns", "app_server", "web_server", "external_api"],
        estimated_duration_minutes=20,
        blast_radius="all services using DNS",
        prerequisites=["monitoring"],
        tags=["latency", "dns", "advanced"],
    ),

    # ── DATA (3) ──
    ExperimentTemplate(
        id="data-001",
        name="Database Failover",
        category=ExperimentCategory.DATA,
        difficulty=Difficulty.ADVANCED,
        description="Force a primary database failover to a replica.",
        hypothesis="The replica promotes to primary within RTO and applications reconnect seamlessly.",
        steady_state="Database replication lag < 1s, all writes succeed.",
        injection_method="Stop the primary database process or disconnect it from the network.",
        expected_outcome="Replica promotes; applications reconnect; write availability restored within RTO.",
        rollback_steps=["Restart old primary as replica", "Verify replication resumes", "Check data consistency"],
        applicable_component_types=["database"],
        estimated_duration_minutes=30,
        blast_radius="database cluster",
        prerequisites=["failover configured", "replicas > 1", "monitoring"],
        tags=["data", "database", "failover", "advanced"],
    ),
    ExperimentTemplate(
        id="data-002",
        name="Cache Invalidation Storm",
        category=ExperimentCategory.DATA,
        difficulty=Difficulty.INTERMEDIATE,
        description="Flush all cache entries simultaneously to simulate a cache stampede.",
        hypothesis="The backend absorbs the cache-miss traffic without overloading.",
        steady_state="Cache hit ratio > 90%, backend CPU < 50%.",
        injection_method="Execute FLUSHALL or equivalent on the cache cluster.",
        expected_outcome="Backend load spikes but stays within capacity; cache warms up within expected time.",
        rollback_steps=["Allow cache to naturally repopulate", "Monitor backend load during warming"],
        applicable_component_types=["cache", "database", "app_server"],
        estimated_duration_minutes=20,
        blast_radius="cache cluster + backend",
        prerequisites=["monitoring"],
        tags=["data", "cache", "stampede", "intermediate"],
    ),
    ExperimentTemplate(
        id="data-003",
        name="Storage Volume Full",
        category=ExperimentCategory.DATA,
        difficulty=Difficulty.INTERMEDIATE,
        description="Fill a storage volume to capacity to test handling of disk-full conditions.",
        hypothesis="The application handles disk-full gracefully — logs errors, rejects writes, but stays available for reads.",
        steady_state="Disk usage < 70%, all read/write operations succeed.",
        injection_method="Write a large file to fill the volume to 100%.",
        expected_outcome="Write operations fail gracefully; read operations continue; alerts fire.",
        rollback_steps=["Remove the filler file", "Verify write operations resume"],
        applicable_component_types=["database", "storage", "app_server"],
        estimated_duration_minutes=15,
        blast_radius="single volume",
        prerequisites=["monitoring", "backup enabled"],
        tags=["data", "storage", "disk-full", "intermediate"],
    ),

    # ── SECURITY (3) ──
    ExperimentTemplate(
        id="sec-001",
        name="TLS Certificate Expiry",
        category=ExperimentCategory.SECURITY,
        difficulty=Difficulty.INTERMEDIATE,
        description="Replace a TLS certificate with an expired one to verify detection and handling.",
        hypothesis="Monitoring detects the expired certificate; clients fail gracefully with clear errors.",
        steady_state="TLS handshakes succeed, certificate validity > 30 days.",
        injection_method="Deploy an expired certificate on the target service.",
        expected_outcome="Alerts fire; clients receive clear TLS errors; no silent data transmission over broken TLS.",
        rollback_steps=["Restore the valid certificate", "Restart the service if needed"],
        applicable_component_types=["web_server", "app_server", "load_balancer", "external_api"],
        estimated_duration_minutes=15,
        blast_radius="single service",
        prerequisites=["monitoring", "encryption in transit"],
        tags=["security", "tls", "certificate", "intermediate"],
    ),
    ExperimentTemplate(
        id="sec-002",
        name="Authentication Service Failure",
        category=ExperimentCategory.SECURITY,
        difficulty=Difficulty.ADVANCED,
        description="Take down the authentication/identity service.",
        hypothesis="Services degrade gracefully — existing sessions continue, new logins are blocked with clear messaging.",
        steady_state="Authentication latency < 100ms, success rate > 99.9%.",
        injection_method="Block network access to the auth service or stop it.",
        expected_outcome="Existing sessions work via cached tokens; new auth fails gracefully; no data leakage.",
        rollback_steps=["Restore auth service", "Clear invalid session caches", "Verify auth flow end-to-end"],
        applicable_component_types=["app_server", "external_api"],
        estimated_duration_minutes=30,
        blast_radius="all authenticated services",
        prerequisites=["monitoring", "health check configured"],
        tags=["security", "authentication", "advanced"],
    ),
    ExperimentTemplate(
        id="sec-003",
        name="Secret Rotation Under Load",
        category=ExperimentCategory.SECURITY,
        difficulty=Difficulty.EXPERT,
        description="Rotate database credentials and API keys while under production-like load.",
        hypothesis="Secret rotation completes without service interruption or connection failures.",
        steady_state="All connections use valid credentials, error rate < 0.1%.",
        injection_method="Trigger secret rotation via vault/secrets-manager while running load test.",
        expected_outcome="Old credentials are replaced; connections re-establish; no auth failures during transition.",
        rollback_steps=["Restore old credentials if rotation fails", "Restart connection pools", "Verify all services reconnect"],
        applicable_component_types=["database", "cache", "external_api", "app_server"],
        estimated_duration_minutes=30,
        blast_radius="all services using rotated secret",
        prerequisites=["monitoring", "rollback procedure documented"],
        tags=["security", "secrets", "rotation", "expert"],
    ),

    # ── CAPACITY (3) ──
    ExperimentTemplate(
        id="cap-001",
        name="CPU Stress Test",
        category=ExperimentCategory.CAPACITY,
        difficulty=Difficulty.BEGINNER,
        description="Consume CPU resources on a target node to test autoscaling and degradation.",
        hypothesis="Autoscaling triggers within configured thresholds; service remains responsive.",
        steady_state="CPU usage < 40%, response time < 100ms.",
        injection_method="Run stress-ng or similar CPU-intensive workload on the target.",
        expected_outcome="Autoscaler adds replicas; latency increases but stays within SLO.",
        rollback_steps=["Stop the stress workload", "Allow autoscaler to scale down"],
        applicable_component_types=["app_server", "web_server"],
        estimated_duration_minutes=15,
        blast_radius="single node",
        prerequisites=["monitoring", "autoscaling enabled"],
        tags=["capacity", "cpu", "autoscaling", "beginner"],
    ),
    ExperimentTemplate(
        id="cap-002",
        name="Memory Exhaustion",
        category=ExperimentCategory.CAPACITY,
        difficulty=Difficulty.INTERMEDIATE,
        description="Gradually consume memory on a target to test OOM handling.",
        hypothesis="The system detects memory pressure and sheds load or scales before OOM kill.",
        steady_state="Memory usage < 60%, no OOM events.",
        injection_method="Allocate memory incrementally using stress-ng --vm.",
        expected_outcome="OOM killer targets the injected process, not the application; alerts fire.",
        rollback_steps=["Stop the memory stress workload", "Verify application processes are intact"],
        applicable_component_types=["app_server", "web_server", "database", "cache"],
        estimated_duration_minutes=20,
        blast_radius="single node",
        prerequisites=["monitoring"],
        tags=["capacity", "memory", "oom", "intermediate"],
    ),
    ExperimentTemplate(
        id="cap-003",
        name="Connection Pool Saturation",
        category=ExperimentCategory.CAPACITY,
        difficulty=Difficulty.INTERMEDIATE,
        description="Exhaust the connection pool of a service to test pool management and queuing.",
        hypothesis="The service queues or rejects new connections gracefully without crashing.",
        steady_state="Connection pool usage < 50%, no connection errors.",
        injection_method="Open and hold connections up to the pool limit using a load generator.",
        expected_outcome="New requests are queued or receive 503; no crashes; pool recovers after release.",
        rollback_steps=["Release held connections", "Reset connection pool if needed"],
        applicable_component_types=["database", "app_server", "cache"],
        estimated_duration_minutes=20,
        blast_radius="single service",
        prerequisites=["monitoring"],
        tags=["capacity", "connections", "pool", "intermediate"],
    ),

    # ── DEPENDENCY (3) ──
    ExperimentTemplate(
        id="dep-001",
        name="Downstream Service Outage",
        category=ExperimentCategory.DEPENDENCY,
        difficulty=Difficulty.INTERMEDIATE,
        description="Block traffic to a downstream dependency to test circuit breaker and fallback behaviour.",
        hypothesis="The circuit breaker opens and the service returns degraded but functional responses.",
        steady_state="All downstream calls succeed, error rate < 0.1%.",
        injection_method="Use iptables/network policy to block traffic to the downstream service.",
        expected_outcome="Circuit breaker trips; fallback responses returned; upstream services unaffected.",
        rollback_steps=["Remove network block", "Reset circuit breaker state", "Verify downstream connectivity"],
        applicable_component_types=["app_server", "web_server", "external_api"],
        estimated_duration_minutes=20,
        blast_radius="service-to-service",
        prerequisites=["monitoring", "circuit breaker enabled"],
        tags=["dependency", "circuit-breaker", "outage", "intermediate"],
    ),
    ExperimentTemplate(
        id="dep-002",
        name="External API Degradation",
        category=ExperimentCategory.DEPENDENCY,
        difficulty=Difficulty.INTERMEDIATE,
        description="Simulate a third-party API returning errors or timing out.",
        hypothesis="The application handles external API failures without cascading to other features.",
        steady_state="External API calls succeed, feature availability 100%.",
        injection_method="Intercept API calls via proxy and return 500 or inject 10s delay.",
        expected_outcome="Affected feature degrades; unrelated features remain fully operational.",
        rollback_steps=["Remove proxy interception", "Verify external API connectivity"],
        applicable_component_types=["external_api", "app_server"],
        estimated_duration_minutes=20,
        blast_radius="single integration",
        prerequisites=["monitoring"],
        tags=["dependency", "external-api", "degradation", "intermediate"],
    ),
    ExperimentTemplate(
        id="dep-003",
        name="Message Queue Backpressure",
        category=ExperimentCategory.DEPENDENCY,
        difficulty=Difficulty.ADVANCED,
        description="Stop consumers to let the message queue fill up and test backpressure handling.",
        hypothesis="Producers handle queue-full conditions via backpressure without losing messages.",
        steady_state="Queue depth < 1000, consumer lag < 10s.",
        injection_method="Stop all consumer processes while maintaining producer load.",
        expected_outcome="Producers slow down or buffer; no message loss; consumers catch up after restart.",
        rollback_steps=["Restart consumer processes", "Monitor consumer lag until caught up"],
        applicable_component_types=["queue", "app_server"],
        estimated_duration_minutes=30,
        blast_radius="queue cluster + consumers",
        prerequisites=["monitoring"],
        tags=["dependency", "queue", "backpressure", "advanced"],
    ),

    # ── STATE (2) ──
    ExperimentTemplate(
        id="state-001",
        name="Split-Brain Scenario",
        category=ExperimentCategory.STATE,
        difficulty=Difficulty.EXPERT,
        description="Create a network partition between cluster nodes to test split-brain resolution.",
        hypothesis="The cluster detects split-brain and resolves it without data corruption.",
        steady_state="Cluster consensus is healthy, all nodes agree on leader.",
        injection_method="Use iptables to partition the cluster into two groups.",
        expected_outcome="Minority partition becomes read-only or stops; majority continues; no data corruption.",
        rollback_steps=["Remove network partition", "Verify cluster reconverges", "Check data consistency"],
        applicable_component_types=["database", "cache"],
        estimated_duration_minutes=45,
        blast_radius="cluster-wide",
        prerequisites=["monitoring", "replicas > 1"],
        tags=["state", "split-brain", "partition", "expert"],
    ),
    ExperimentTemplate(
        id="state-002",
        name="Clock Skew Injection",
        category=ExperimentCategory.STATE,
        difficulty=Difficulty.ADVANCED,
        description="Skew the system clock on a node to test time-dependent logic.",
        hypothesis="The application tolerates clock skew without data corruption or auth failures.",
        steady_state="NTP sync within 1ms, all time-dependent operations succeed.",
        injection_method="Use date --set or libfaketime to skew the clock by +-5 minutes.",
        expected_outcome="Time-based tokens/certs may fail; application handles it gracefully; alerts fire.",
        rollback_steps=["Restore system clock", "Force NTP re-sync", "Verify time-dependent operations"],
        applicable_component_types=["app_server", "database", "cache"],
        estimated_duration_minutes=20,
        blast_radius="single node",
        prerequisites=["monitoring"],
        tags=["state", "clock-skew", "time", "advanced"],
    ),

    # ── CONFIGURATION (2) ──
    ExperimentTemplate(
        id="config-001",
        name="Configuration Rollback",
        category=ExperimentCategory.CONFIGURATION,
        difficulty=Difficulty.BEGINNER,
        description="Deploy a bad configuration and verify rollback works.",
        hypothesis="The system detects the bad config and rolls back automatically or alerts for manual rollback.",
        steady_state="Application running with known-good configuration.",
        injection_method="Deploy a configuration with an invalid value (e.g. wrong DB host).",
        expected_outcome="Health checks fail; automated rollback triggers or alerts fire; service recovers.",
        rollback_steps=["Redeploy the known-good configuration", "Verify service health"],
        applicable_component_types=["app_server", "web_server", "database", "cache", "load_balancer"],
        estimated_duration_minutes=10,
        blast_radius="single service",
        prerequisites=["monitoring", "rollback procedure documented"],
        tags=["configuration", "rollback", "beginner"],
    ),
    ExperimentTemplate(
        id="config-002",
        name="Feature Flag Toggle Storm",
        category=ExperimentCategory.CONFIGURATION,
        difficulty=Difficulty.INTERMEDIATE,
        description="Rapidly toggle feature flags to test flag evaluation caching and race conditions.",
        hypothesis="Feature flag changes propagate consistently without race conditions or stale reads.",
        steady_state="Feature flags evaluated correctly, flag service latency < 10ms.",
        injection_method="Toggle a feature flag on/off repeatedly at high frequency.",
        expected_outcome="Flag evaluation is consistent; no crashes from race conditions; eventual convergence.",
        rollback_steps=["Set feature flag to a stable state", "Clear flag caches if needed"],
        applicable_component_types=["app_server", "web_server"],
        estimated_duration_minutes=15,
        blast_radius="services using the flag",
        prerequisites=["monitoring"],
        tags=["configuration", "feature-flag", "intermediate"],
    ),
]

_TEMPLATE_INDEX: dict[str, ExperimentTemplate] = {t.id: t for t in _BUILTIN_TEMPLATES}


# ---------------------------------------------------------------------------
# Component type → category relevance mapping
# ---------------------------------------------------------------------------

_COMPONENT_CATEGORY_RELEVANCE: dict[str, list[ExperimentCategory]] = {
    ComponentType.LOAD_BALANCER.value: [
        ExperimentCategory.AVAILABILITY,
        ExperimentCategory.LATENCY,
        ExperimentCategory.CONFIGURATION,
    ],
    ComponentType.WEB_SERVER.value: [
        ExperimentCategory.AVAILABILITY,
        ExperimentCategory.LATENCY,
        ExperimentCategory.CAPACITY,
        ExperimentCategory.CONFIGURATION,
    ],
    ComponentType.APP_SERVER.value: [
        ExperimentCategory.AVAILABILITY,
        ExperimentCategory.LATENCY,
        ExperimentCategory.CAPACITY,
        ExperimentCategory.DEPENDENCY,
        ExperimentCategory.SECURITY,
        ExperimentCategory.CONFIGURATION,
    ],
    ComponentType.DATABASE.value: [
        ExperimentCategory.AVAILABILITY,
        ExperimentCategory.DATA,
        ExperimentCategory.LATENCY,
        ExperimentCategory.CAPACITY,
        ExperimentCategory.STATE,
    ],
    ComponentType.CACHE.value: [
        ExperimentCategory.DATA,
        ExperimentCategory.CAPACITY,
        ExperimentCategory.STATE,
        ExperimentCategory.LATENCY,
    ],
    ComponentType.QUEUE.value: [
        ExperimentCategory.DEPENDENCY,
        ExperimentCategory.CAPACITY,
        ExperimentCategory.AVAILABILITY,
    ],
    ComponentType.STORAGE.value: [
        ExperimentCategory.DATA,
        ExperimentCategory.CAPACITY,
        ExperimentCategory.AVAILABILITY,
    ],
    ComponentType.DNS.value: [
        ExperimentCategory.LATENCY,
        ExperimentCategory.AVAILABILITY,
    ],
    ComponentType.EXTERNAL_API.value: [
        ExperimentCategory.DEPENDENCY,
        ExperimentCategory.LATENCY,
        ExperimentCategory.SECURITY,
    ],
    ComponentType.CUSTOM.value: [
        ExperimentCategory.AVAILABILITY,
        ExperimentCategory.CONFIGURATION,
    ],
}


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class ChaosExperimentLibraryEngine:
    """Curated library of chaos experiment templates with recommendation logic."""

    def __init__(self, templates: list[ExperimentTemplate] | None = None) -> None:
        if templates is not None:
            self._templates = list(templates)
            self._index = {t.id: t for t in self._templates}
        else:
            self._templates = list(_BUILTIN_TEMPLATES)
            self._index = dict(_TEMPLATE_INDEX)

    # -- public properties ---------------------------------------------------

    @property
    def templates(self) -> list[ExperimentTemplate]:
        return list(self._templates)

    @property
    def template_count(self) -> int:
        return len(self._templates)

    # -- query methods -------------------------------------------------------

    def list_templates(
        self,
        category: ExperimentCategory | None = None,
        difficulty: Difficulty | None = None,
    ) -> list[ExperimentTemplate]:
        """Return templates, optionally filtered by category and/or difficulty."""
        result = self._templates
        if category is not None:
            result = [t for t in result if t.category == category]
        if difficulty is not None:
            result = [t for t in result if t.difficulty == difficulty]
        return result

    def get_template(self, template_id: str) -> ExperimentTemplate | None:
        """Look up a template by its unique id."""
        return self._index.get(template_id)

    def filter_by_component_type(self, component_type: str) -> list[ExperimentTemplate]:
        """Return all templates applicable to the given component type."""
        ct = component_type.lower()
        return [
            t for t in self._templates
            if ct in [a.lower() for a in t.applicable_component_types]
        ]

    # -- recommendation methods ----------------------------------------------

    def recommend_experiments(
        self,
        graph: InfraGraph,
    ) -> list[ExperimentRecommendation]:
        """Recommend experiments for each component in the graph."""
        recommendations: list[ExperimentRecommendation] = []

        for comp in graph.components.values():
            comp_type = comp.type.value
            applicable = self.filter_by_component_type(comp_type)

            # Sort by relevance: category relevance order, then difficulty
            relevant_cats = _COMPONENT_CATEGORY_RELEVANCE.get(comp_type, [])

            for tmpl in applicable:
                score = self._compute_relevance(tmpl, comp, graph, relevant_cats)
                priority = self._priority_from_score(score)
                reason = self._build_reason(tmpl, comp, graph)

                recommendations.append(
                    ExperimentRecommendation(
                        template=tmpl,
                        target_component=comp.id,
                        relevance_score=round(score, 3),
                        reason=reason,
                        priority=priority,
                    )
                )

        # Sort by relevance_score descending
        recommendations.sort(key=lambda r: r.relevance_score, reverse=True)
        return recommendations

    def generate_experiment_plan(
        self,
        graph: InfraGraph,
        max_experiments: int = 10,
    ) -> ExperimentPlan:
        """Generate an ordered experiment plan for the infrastructure."""
        recs = self.recommend_experiments(graph)

        # Deduplicate: pick top recommendation per (template_id, component) pair
        seen: set[tuple[str, str]] = set()
        unique_recs: list[ExperimentRecommendation] = []
        for rec in recs:
            key = (rec.template.id, rec.target_component)
            if key not in seen:
                seen.add(key)
                unique_recs.append(rec)

        # Group by priority, pick from each to ensure diversity
        selected = unique_recs[:max_experiments]

        entries: list[ExperimentPlanEntry] = []
        categories_covered: set[str] = set()
        components_covered: set[str] = set()
        total_minutes = 0

        for i, rec in enumerate(selected, start=1):
            entries.append(
                ExperimentPlanEntry(
                    order=i,
                    template=rec.template,
                    target_component=rec.target_component,
                    reason=rec.reason,
                    priority=rec.priority,
                )
            )
            categories_covered.add(rec.template.category.value)
            components_covered.add(rec.target_component)
            total_minutes += rec.template.estimated_duration_minutes

        return ExperimentPlan(
            entries=entries,
            total_estimated_minutes=total_minutes,
            categories_covered=sorted(categories_covered),
            components_covered=sorted(components_covered),
        )

    def validate_prerequisites(
        self,
        graph: InfraGraph,
        template: ExperimentTemplate,
        component_id: str | None = None,
    ) -> PrerequisiteCheck:
        """Check which prerequisites are met/unmet for a template in the given graph."""
        met: list[str] = []
        unmet: list[str] = []
        warnings: list[str] = []

        for prereq in template.prerequisites:
            if _check_prerequisite(prereq, graph, component_id):
                met.append(prereq)
            else:
                unmet.append(prereq)

        # Extra warnings
        if not graph.components:
            warnings.append("Graph has no components")

        if template.difficulty in (Difficulty.ADVANCED, Difficulty.EXPERT):
            warnings.append(
                f"This is a {template.difficulty.value}-level experiment — ensure experienced operators are available"
            )

        return PrerequisiteCheck(
            template_id=template.id,
            satisfied=len(unmet) == 0,
            met=met,
            unmet=unmet,
            warnings=warnings,
        )

    def estimate_coverage(
        self,
        graph: InfraGraph,
        completed_experiments: list[tuple[str, str]],
    ) -> CoverageReport:
        """Estimate chaos experiment coverage.

        *completed_experiments* is a list of (template_id, component_id) pairs
        representing experiments that have already been executed.
        """
        all_categories = {c.value for c in ExperimentCategory}
        covered_categories: set[str] = set()
        component_coverage: dict[str, list[str]] = {}

        covered_component_ids: set[str] = set()

        for tmpl_id, comp_id in completed_experiments:
            tmpl = self.get_template(tmpl_id)
            if tmpl is None:
                continue
            covered_categories.add(tmpl.category.value)
            covered_component_ids.add(comp_id)
            component_coverage.setdefault(comp_id, [])
            if tmpl.category.value not in component_coverage[comp_id]:
                component_coverage[comp_id].append(tmpl.category.value)

        total = len(graph.components)
        covered = len(covered_component_ids & set(graph.components.keys()))
        pct = (covered / total * 100.0) if total > 0 else 0.0

        untested = sorted(all_categories - covered_categories)
        recommendations: list[str] = []
        if untested:
            recommendations.append(
                f"No experiments have been run for categories: {', '.join(untested)}"
            )

        uncovered_comps = set(graph.components.keys()) - covered_component_ids
        if uncovered_comps:
            recommendations.append(
                f"{len(uncovered_comps)} component(s) have no chaos experiments: "
                + ", ".join(sorted(uncovered_comps))
            )

        return CoverageReport(
            total_components=total,
            covered_components=covered,
            coverage_percent=round(pct, 2),
            categories_tested=sorted(covered_categories),
            categories_untested=untested,
            component_coverage=component_coverage,
            recommendations=recommendations,
        )

    # -- internal helpers ----------------------------------------------------

    def _compute_relevance(
        self,
        template: ExperimentTemplate,
        comp: object,
        graph: InfraGraph,
        relevant_cats: list[ExperimentCategory],
    ) -> float:
        """Score 0..1 for how relevant a template is to a component."""
        score = 0.5  # baseline

        # Category relevance boost
        if template.category in relevant_cats:
            idx = relevant_cats.index(template.category)
            score += 0.2 * (1.0 - idx / max(len(relevant_cats), 1))

        # Difficulty adjustment — lower difficulty = slightly higher score for beginners
        difficulty_bonus = {
            Difficulty.BEGINNER: 0.1,
            Difficulty.INTERMEDIATE: 0.05,
            Difficulty.ADVANCED: 0.0,
            Difficulty.EXPERT: -0.05,
        }
        score += difficulty_bonus.get(template.difficulty, 0.0)

        # Component health: degraded/overloaded components get a boost
        comp_obj = comp  # type: ignore[assignment]
        if hasattr(comp_obj, "health"):
            if comp_obj.health == HealthStatus.DEGRADED:
                score += 0.1
            elif comp_obj.health == HealthStatus.OVERLOADED:
                score += 0.15

        # High dependency count = higher relevance for dependency experiments
        if hasattr(comp_obj, "id"):
            deps = graph.get_dependencies(comp_obj.id)
            dependents = graph.get_dependents(comp_obj.id)
            dep_count = len(deps) + len(dependents)
            if dep_count > 3 and template.category == ExperimentCategory.DEPENDENCY:
                score += 0.1
            if dep_count > 5:
                score += 0.05

        # Clamp
        return max(0.0, min(1.0, score))

    @staticmethod
    def _priority_from_score(score: float) -> str:
        if score >= 0.8:
            return "critical"
        if score >= 0.6:
            return "high"
        if score >= 0.4:
            return "medium"
        return "low"

    @staticmethod
    def _build_reason(
        template: ExperimentTemplate,
        comp: object,
        graph: InfraGraph,
    ) -> str:
        parts: list[str] = []
        comp_obj = comp  # type: ignore[assignment]

        if hasattr(comp_obj, "type"):
            parts.append(
                f"Component type '{comp_obj.type.value}' is applicable to '{template.name}'"
            )

        if hasattr(comp_obj, "replicas") and comp_obj.replicas == 1:
            if template.category == ExperimentCategory.AVAILABILITY:
                parts.append("Single replica increases availability risk")

        if hasattr(comp_obj, "health"):
            if comp_obj.health in (HealthStatus.DEGRADED, HealthStatus.OVERLOADED):
                parts.append(f"Component is currently {comp_obj.health.value}")

        if hasattr(comp_obj, "id"):
            affected = graph.get_all_affected(comp_obj.id)
            if affected:
                parts.append(f"Failure could affect {len(affected)} downstream component(s)")

        return "; ".join(parts) if parts else "General applicability"
