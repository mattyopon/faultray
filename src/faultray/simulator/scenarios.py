"""Chaos scenarios - defines what failures to simulate."""

from __future__ import annotations

from enum import Enum
from itertools import combinations
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field, field_validator

if TYPE_CHECKING:
    from faultray.simulator.traffic import TrafficPattern


class FaultType(str, Enum):
    COMPONENT_DOWN = "component_down"
    LATENCY_SPIKE = "latency_spike"
    CPU_SATURATION = "cpu_saturation"
    MEMORY_EXHAUSTION = "memory_exhaustion"
    DISK_FULL = "disk_full"
    CONNECTION_POOL_EXHAUSTION = "connection_pool_exhaustion"
    NETWORK_PARTITION = "network_partition"
    TRAFFIC_SPIKE = "traffic_spike"
    HALLUCINATION = "hallucination"
    CONTEXT_OVERFLOW = "context_overflow"
    LLM_RATE_LIMIT = "llm_rate_limit"
    TOKEN_EXHAUSTION = "token_exhaustion"
    TOOL_FAILURE = "tool_failure"
    AGENT_LOOP = "agent_loop"
    PROMPT_INJECTION = "prompt_injection"


class Fault(BaseModel):
    """A single fault injection."""

    target_component_id: str
    fault_type: FaultType
    severity: float = 1.0  # 0.0 (mild) to 1.0 (total failure)
    duration_seconds: int = 300
    parameters: dict[str, float | int | str] = Field(default_factory=dict)


class Scenario(BaseModel):
    """A chaos scenario consisting of one or more faults."""

    id: str
    name: str
    description: str
    faults: list[Fault]
    traffic_multiplier: float = 1.0  # 1.0 = normal, 2.0 = double traffic

    @field_validator('traffic_multiplier')
    @classmethod
    def validate_multiplier(cls, v):
        if v < 0:
            raise ValueError(f"traffic_multiplier must be >= 0, got {v}")
        return v


class DynamicScenario(BaseModel):
    """A chaos scenario with time-varying traffic patterns."""

    id: str
    name: str
    description: str
    faults: list[Fault]
    traffic_pattern: TrafficPattern | None = None
    duration_seconds: int = 300
    time_step_seconds: int = 5

    @field_validator('duration_seconds', 'time_step_seconds')
    @classmethod
    def validate_positive(cls, v):
        if v <= 0:
            raise ValueError(f"Duration/step must be > 0, got {v}")
        return v


def _categorize(components: dict | None, component_ids: list[str]) -> dict[str, list[str]]:
    """Categorize components by type."""
    cats: dict[str, list[str]] = {
        "databases": [], "caches": [], "app_servers": [], "load_balancers": [],
        "queues": [], "storage": [], "dns": [], "web_servers": [], "other": [],
    }
    if components:
        for comp_id, comp in components.items():
            ctype = comp.type.value if hasattr(comp.type, "value") else str(comp.type)
            if ctype == "database":
                cats["databases"].append(comp_id)
            elif ctype == "cache":
                cats["caches"].append(comp_id)
            elif ctype == "app_server":
                cats["app_servers"].append(comp_id)
            elif ctype == "web_server":
                cats["web_servers"].append(comp_id)
            elif ctype == "load_balancer":
                cats["load_balancers"].append(comp_id)
            elif ctype == "queue":
                cats["queues"].append(comp_id)
            elif ctype == "storage":
                cats["storage"].append(comp_id)
            elif ctype == "dns":
                cats["dns"].append(comp_id)
            else:
                cats["other"].append(comp_id)
    else:
        cats["other"] = list(component_ids)
    return cats


def _host_groups(components: dict | None) -> dict[str, list[str]]:
    """Group components by host for zone/rack failure scenarios."""
    groups: dict[str, list[str]] = {}
    if not components:
        return groups
    for comp_id, comp in components.items():
        host = comp.host or "unknown"
        groups.setdefault(host, []).append(comp_id)
    return groups


def generate_default_scenarios(
    component_ids: list[str],
    components: dict | None = None,
) -> list[Scenario]:
    """Generate comprehensive chaos scenarios.

    Generates scenarios across 20 categories covering single faults, compound faults,
    resource exhaustion, traffic patterns, network failures, and more.
    """
    scenarios: list[Scenario] = []
    cats = _categorize(components, component_ids)

    db = cats["databases"]
    cache = cats["caches"]
    app = cats["app_servers"] + cats["web_servers"]
    lb = cats["load_balancers"]
    queue = cats["queues"]
    stor = cats["storage"]
    dns = cats["dns"]

    # =========================================================================
    # CATEGORY 1: Single component failure (every component)
    # =========================================================================
    for cid in component_ids:
        scenarios.append(Scenario(
            id=f"single-failure-{cid}", name=f"Single failure: {cid}",
            description=f"Complete failure of {cid}",
            faults=[Fault(target_component_id=cid, fault_type=FaultType.COMPONENT_DOWN)],
        ))

    # =========================================================================
    # CATEGORY 2: CPU saturation (every component)
    # =========================================================================
    for cid in component_ids:
        scenarios.append(Scenario(
            id=f"cpu-saturation-{cid}", name=f"CPU saturation: {cid}",
            description=f"CPU reaches 100% on {cid}, all processing stalls",
            faults=[Fault(target_component_id=cid, fault_type=FaultType.CPU_SATURATION)],
        ))

    # =========================================================================
    # CATEGORY 3: Memory exhaustion (every component)
    # =========================================================================
    for cid in component_ids:
        scenarios.append(Scenario(
            id=f"oom-{cid}", name=f"OOM kill: {cid}",
            description=f"Memory exhaustion on {cid} triggers OOM killer",
            faults=[Fault(target_component_id=cid, fault_type=FaultType.MEMORY_EXHAUSTION)],
        ))

    # =========================================================================
    # CATEGORY 4: Connection pool exhaustion (DB + App + Cache)
    # =========================================================================
    pool_targets = db + app + cache if components else component_ids
    for cid in pool_targets:
        scenarios.append(Scenario(
            id=f"pool-exhaustion-{cid}", name=f"Pool exhaustion: {cid}",
            description=f"All connection pool slots consumed on {cid}, new requests rejected",
            faults=[Fault(target_component_id=cid, fault_type=FaultType.CONNECTION_POOL_EXHAUSTION)],
        ))

    # =========================================================================
    # CATEGORY 5: Disk full (DB + Storage + App + Queue)
    # =========================================================================
    disk_targets = db + stor + app + queue if components else component_ids
    for cid in disk_targets:
        scenarios.append(Scenario(
            id=f"disk-full-{cid}", name=f"Disk full: {cid}",
            description=f"Disk reaches 100% on {cid}, writes fail",
            faults=[Fault(target_component_id=cid, fault_type=FaultType.DISK_FULL)],
        ))

    # =========================================================================
    # CATEGORY 6: Network partition (every component)
    # =========================================================================
    for cid in component_ids:
        scenarios.append(Scenario(
            id=f"net-partition-{cid}", name=f"Network partition: {cid}",
            description=f"Network partition isolates {cid} from all other components",
            faults=[Fault(target_component_id=cid, fault_type=FaultType.NETWORK_PARTITION)],
        ))

    # =========================================================================
    # CATEGORY 7: Latency spike (every component, varying severity)
    # =========================================================================
    for cid in component_ids:
        scenarios.append(Scenario(
            id=f"latency-5x-{cid}", name=f"Latency 5x: {cid}",
            description=f"Response time increases 5x on {cid}",
            faults=[Fault(target_component_id=cid, fault_type=FaultType.LATENCY_SPIKE,
                          parameters={"multiplier": 5})],
        ))
    for cid in db:
        scenarios.append(Scenario(
            id=f"latency-20x-{cid}", name=f"DB latency 20x: {cid}",
            description=f"Severe slow query or lock contention on {cid}, 20x latency",
            faults=[Fault(target_component_id=cid, fault_type=FaultType.LATENCY_SPIKE,
                          parameters={"multiplier": 20})],
        ))

    # =========================================================================
    # CATEGORY 8: Traffic spike (graduated: 1.5x, 2x, 3x, 5x, 10x)
    # =========================================================================
    for mult, desc in [(1.5, "moderate increase"), (2, "doubles"), (3, "peak hour"),
                       (5, "viral event"), (10, "DDoS-level")]:
        scenarios.append(Scenario(
            id=f"traffic-{mult}x", name=f"Traffic spike ({mult}x)",
            description=f"Traffic {desc} ({mult}x normal) across all entry points",
            faults=[], traffic_multiplier=mult,
        ))

    # =========================================================================
    # CATEGORY 9: Pairwise compound failures (every combination of 2)
    # =========================================================================
    for a, b in combinations(component_ids, 2):
        scenarios.append(Scenario(
            id=f"pair-{a}-{b}", name=f"Pair failure: {a} + {b}",
            description=f"Simultaneous failure of {a} and {b}",
            faults=[
                Fault(target_component_id=a, fault_type=FaultType.COMPONENT_DOWN),
                Fault(target_component_id=b, fault_type=FaultType.COMPONENT_DOWN),
            ],
        ))

    # =========================================================================
    # CATEGORY 10: Triple failures (every combination of 3, if <= 10 components)
    # =========================================================================
    if len(component_ids) <= 10:
        for combo in combinations(component_ids, 3):
            ids_str = " + ".join(combo)
            scenarios.append(Scenario(
                id=f"triple-{'-'.join(combo)}", name=f"Triple failure: {ids_str}",
                description=f"Simultaneous failure of {ids_str}",
                faults=[Fault(target_component_id=c, fault_type=FaultType.COMPONENT_DOWN)
                        for c in combo],
            ))

    # =========================================================================
    # CATEGORY 11: Cache stampede (cache down + traffic spike)
    # =========================================================================
    for cid in cache:
        for mult in [2.0, 5.0]:
            scenarios.append(Scenario(
                id=f"stampede-{cid}-{mult}x", name=f"Cache stampede: {cid} + {mult}x traffic",
                description=f"Cache {cid} fails, all requests hit DB. Traffic at {mult}x. Thundering herd pattern.",
                faults=[Fault(target_component_id=cid, fault_type=FaultType.COMPONENT_DOWN)],
                traffic_multiplier=mult,
            ))

    # =========================================================================
    # CATEGORY 12: Component down + traffic spike (every component × traffic levels)
    # =========================================================================
    for cid in component_ids:
        for mult in [2.0, 3.0]:
            scenarios.append(Scenario(
                id=f"down-traffic-{cid}-{mult}x",
                name=f"{cid} down + {mult}x traffic",
                description=f"{cid} fails during {mult}x traffic surge. Remaining components must absorb load.",
                faults=[Fault(target_component_id=cid, fault_type=FaultType.COMPONENT_DOWN)],
                traffic_multiplier=mult,
            ))

    # =========================================================================
    # CATEGORY 13: Zone / host failure (all components on same host fail)
    # =========================================================================
    hosts = _host_groups(components)
    for host, host_comps in hosts.items():
        if len(host_comps) >= 2:
            scenarios.append(Scenario(
                id=f"zone-failure-{host}", name=f"Zone failure: host {host}",
                description=f"All components on host {host} fail simultaneously ({len(host_comps)} components)",
                faults=[Fault(target_component_id=c, fault_type=FaultType.COMPONENT_DOWN)
                        for c in host_comps],
            ))

    # =========================================================================
    # CATEGORY 14: DB-specific deep scenarios
    # =========================================================================
    for cid in db:
        # Slow query log explosion fills disk
        scenarios.append(Scenario(
            id=f"log-explosion-{cid}", name=f"Log explosion: {cid}",
            description=f"Slow query logs / WAL on {cid} fill disk, write operations blocked",
            faults=[Fault(target_component_id=cid, fault_type=FaultType.DISK_FULL,
                          parameters={"cause": "log_explosion"})],
        ))
        # Replication lag (latency + degraded)
        scenarios.append(Scenario(
            id=f"replication-lag-{cid}", name=f"Replication lag: {cid}",
            description=f"Primary-replica lag on {cid} causes stale reads and write backpressure",
            faults=[Fault(target_component_id=cid, fault_type=FaultType.LATENCY_SPIKE,
                          parameters={"multiplier": 10, "cause": "replication_lag"})],
        ))
        # Connection storm after restart
        scenarios.append(Scenario(
            id=f"connection-storm-{cid}", name=f"Connection storm: {cid}",
            description=f"After {cid} restarts, all app servers reconnect simultaneously overwhelming the pool",
            faults=[Fault(target_component_id=cid, fault_type=FaultType.CONNECTION_POOL_EXHAUSTION,
                          parameters={"cause": "reconnection_storm"})],
        ))
        # Long-running transaction locks
        scenarios.append(Scenario(
            id=f"lock-contention-{cid}", name=f"Lock contention: {cid}",
            description=f"Long-running transaction on {cid} holds row locks, blocking all writes",
            faults=[Fault(target_component_id=cid, fault_type=FaultType.LATENCY_SPIKE,
                          parameters={"multiplier": 50, "cause": "lock_contention"})],
        ))

    # =========================================================================
    # CATEGORY 15: Queue-specific scenarios
    # =========================================================================
    for cid in queue:
        # Queue backpressure (disk full from accumulated messages)
        scenarios.append(Scenario(
            id=f"queue-backpressure-{cid}", name=f"Queue backpressure: {cid}",
            description=f"Consumers stall, messages accumulate on {cid} until disk fills",
            faults=[Fault(target_component_id=cid, fault_type=FaultType.DISK_FULL,
                          parameters={"cause": "message_accumulation"})],
        ))
        # Poison message (queue becomes stuck)
        scenarios.append(Scenario(
            id=f"poison-message-{cid}", name=f"Poison message: {cid}",
            description=f"Unprocessable message on {cid} blocks consumer, messages pile up",
            faults=[Fault(target_component_id=cid, fault_type=FaultType.LATENCY_SPIKE,
                          parameters={"cause": "poison_message", "multiplier": 100})],
        ))

    # =========================================================================
    # CATEGORY 16: LB-specific scenarios
    # =========================================================================
    for cid in lb:
        # Health check misconfiguration
        scenarios.append(Scenario(
            id=f"healthcheck-fail-{cid}", name=f"Health check failure: {cid}",
            description=f"LB {cid} marks all backends unhealthy due to health check misconfiguration",
            faults=[Fault(target_component_id=cid, fault_type=FaultType.COMPONENT_DOWN,
                          parameters={"cause": "healthcheck_misconfiguration"})],
        ))
        # TLS certificate expiry
        scenarios.append(Scenario(
            id=f"tls-expiry-{cid}", name=f"TLS cert expired: {cid}",
            description=f"SSL/TLS certificate on {cid} expires, all HTTPS connections rejected",
            faults=[Fault(target_component_id=cid, fault_type=FaultType.COMPONENT_DOWN,
                          parameters={"cause": "tls_cert_expiry"})],
        ))
        # LB config hot-reload failure
        scenarios.append(Scenario(
            id=f"config-reload-{cid}", name=f"Config reload failure: {cid}",
            description=f"Configuration reload on {cid} fails, routing rules corrupted",
            faults=[Fault(target_component_id=cid, fault_type=FaultType.COMPONENT_DOWN,
                          parameters={"cause": "config_reload_failure"})],
        ))

    # =========================================================================
    # CATEGORY 17: App server-specific scenarios
    # =========================================================================
    for cid in app:
        # Memory leak (gradual OOM)
        scenarios.append(Scenario(
            id=f"memory-leak-{cid}", name=f"Memory leak: {cid}",
            description=f"Gradual memory leak on {cid} eventually triggers OOM killer",
            faults=[Fault(target_component_id=cid, fault_type=FaultType.MEMORY_EXHAUSTION,
                          parameters={"cause": "memory_leak"})],
        ))
        # Thread pool exhaustion
        scenarios.append(Scenario(
            id=f"thread-exhaustion-{cid}", name=f"Thread pool exhaustion: {cid}",
            description=f"All worker threads on {cid} blocked on slow downstream calls",
            faults=[Fault(target_component_id=cid, fault_type=FaultType.CONNECTION_POOL_EXHAUSTION,
                          parameters={"cause": "thread_pool_exhaustion"})],
        ))
        # GC pause (JVM / Go / .NET)
        scenarios.append(Scenario(
            id=f"gc-pause-{cid}", name=f"GC pause: {cid}",
            description=f"Long garbage collection pause on {cid} (Stop-the-World), all requests timeout",
            faults=[Fault(target_component_id=cid, fault_type=FaultType.LATENCY_SPIKE,
                          parameters={"cause": "gc_pause", "multiplier": 30})],
        ))
        # Deployment gone wrong (new version crashes)
        scenarios.append(Scenario(
            id=f"bad-deploy-{cid}", name=f"Bad deployment: {cid}",
            description=f"New version deployed to {cid} crashes on startup, component becomes unavailable",
            faults=[Fault(target_component_id=cid, fault_type=FaultType.COMPONENT_DOWN,
                          parameters={"cause": "bad_deployment"})],
        ))

    # =========================================================================
    # CATEGORY 18: Cache-specific scenarios
    # =========================================================================
    for cid in cache:
        # Cache eviction storm
        scenarios.append(Scenario(
            id=f"eviction-storm-{cid}", name=f"Eviction storm: {cid}",
            description=f"Memory pressure on {cid} causes mass key eviction, hit rate drops to 0%",
            faults=[Fault(target_component_id=cid, fault_type=FaultType.MEMORY_EXHAUSTION,
                          parameters={"cause": "eviction_storm"})],
        ))
        # Cache partition (split brain in cluster)
        scenarios.append(Scenario(
            id=f"cache-split-brain-{cid}", name=f"Cache split brain: {cid}",
            description=f"Cluster partition on {cid} causes inconsistent reads across nodes",
            faults=[Fault(target_component_id=cid, fault_type=FaultType.NETWORK_PARTITION,
                          parameters={"cause": "split_brain"})],
        ))

    # =========================================================================
    # CATEGORY 19: DNS-specific scenarios
    # =========================================================================
    for cid in dns:
        scenarios.append(Scenario(
            id=f"dns-failure-{cid}", name=f"DNS failure: {cid}",
            description=f"DNS resolution on {cid} fails, all name-based service discovery breaks",
            faults=[Fault(target_component_id=cid, fault_type=FaultType.COMPONENT_DOWN,
                          parameters={"cause": "dns_failure"})],
        ))
        scenarios.append(Scenario(
            id=f"dns-latency-{cid}", name=f"DNS latency: {cid}",
            description=f"DNS resolution on {cid} takes 5s+ per query, adds latency to every request",
            faults=[Fault(target_component_id=cid, fault_type=FaultType.LATENCY_SPIKE,
                          parameters={"cause": "dns_slow", "multiplier": 50})],
        ))

    # =========================================================================
    # CATEGORY 20: Storage-specific scenarios
    # =========================================================================
    for cid in stor:
        # I/O throttling
        scenarios.append(Scenario(
            id=f"io-throttle-{cid}", name=f"I/O throttling: {cid}",
            description=f"Storage IOPS limit reached on {cid}, all I/O operations queued",
            faults=[Fault(target_component_id=cid, fault_type=FaultType.LATENCY_SPIKE,
                          parameters={"cause": "io_throttling", "multiplier": 20})],
        ))
        # Data corruption
        scenarios.append(Scenario(
            id=f"data-corruption-{cid}", name=f"Data corruption: {cid}",
            description=f"Data integrity check fails on {cid}, storage marked read-only",
            faults=[Fault(target_component_id=cid, fault_type=FaultType.COMPONENT_DOWN,
                          parameters={"cause": "data_corruption"})],
        ))

    # =========================================================================
    # CATEGORY 21: Cascading timeout chain
    # =========================================================================
    # All DBs slow → apps timeout → LB returns 504
    if db and app:
        faults = [Fault(target_component_id=d, fault_type=FaultType.LATENCY_SPIKE,
                        parameters={"multiplier": 15}) for d in db]
        scenarios.append(Scenario(
            id="cascading-timeout", name="Cascading timeout chain",
            description="All databases become slow, causing app server timeouts, LB returns 504 to users",
            faults=faults,
        ))

    # =========================================================================
    # CATEGORY 22: Total infrastructure meltdown
    # =========================================================================
    if len(component_ids) >= 3:
        # 22a: Original "total meltdown" — all components fail simultaneously.
        # Kept for completeness but with very low likelihood (0.05) since
        # simultaneous failure of every component is extremely unrealistic.
        scenarios.append(Scenario(
            id="total-meltdown", name="Total infrastructure meltdown",
            description=(
                "Complete failure of all components simultaneously (worst case, "
                "extremely unlikely — simultaneous all-down)"
            ),
            faults=[Fault(target_component_id=c, fault_type=FaultType.COMPONENT_DOWN)
                    for c in component_ids],
        ))

        # 22b: Cascading meltdown — fault the top 2-3 most-depended-upon
        # components (root causes) and let the cascade engine determine
        # realistic spread.  This is the realistic meltdown path.
        if components:
            # Count how many other components depend on each component
            dependent_counts: dict[str, int] = {}
            for cid in component_ids:
                count = 0
                for other_id in component_ids:
                    if other_id == cid:
                        continue
                    # Check if other_id depends on cid by looking at
                    # component types that are typically upstream
                    # We use a simple heuristic: count references
                    # in the dependency graph (if available later).
                    # For now, count based on component type criticality.
                    pass
                dependent_counts[cid] = count

            # Rank components by type criticality as a proxy for
            # "most depended upon" when we don't have graph edges here.
            # Priority: database > cache > queue > app_server > load_balancer > others
            _type_rank: dict[str, int] = {
                "database": 6, "cache": 5, "dns": 5, "queue": 4,
                "storage": 4, "app_server": 3, "web_server": 3,
                "load_balancer": 2,
            }
            ranked = sorted(
                component_ids,
                key=lambda cid: _type_rank.get(
                    (components[cid].type.value
                     if hasattr(components[cid].type, "value")
                     else str(components[cid].type)),
                    1,
                ),
                reverse=True,
            )
            # Take top 2-3 root-cause components (min 2, max 3)
            root_cause_count = min(3, max(2, len(ranked) // 3))
            root_causes = ranked[:root_cause_count]

            scenarios.append(Scenario(
                id="cascading-meltdown",
                name="Cascading meltdown (root-cause)",
                description=(
                    f"Critical root-cause components fail "
                    f"({', '.join(root_causes)}), cascade engine determines "
                    f"realistic spread through dependency graph"
                ),
                faults=[Fault(target_component_id=c, fault_type=FaultType.COMPONENT_DOWN)
                        for c in root_causes],
            ))

    # =========================================================================
    # CATEGORY 23: Noisy neighbor / resource contention
    # =========================================================================
    for cid in app:
        scenarios.append(Scenario(
            id=f"noisy-neighbor-{cid}", name=f"Noisy neighbor: {cid}",
            description=f"One process on {cid} consumes all CPU, starving the main service",
            faults=[Fault(target_component_id=cid, fault_type=FaultType.CPU_SATURATION,
                          parameters={"cause": "noisy_neighbor"})],
        ))

    # =========================================================================
    # CATEGORY 24: Dependency timeout + traffic (realistic incident pattern)
    # =========================================================================
    for cid in db:
        scenarios.append(Scenario(
            id=f"slow-db-peak-{cid}", name=f"Slow DB at peak: {cid}",
            description=f"DB {cid} latency spikes during peak traffic (3x). Timeouts cascade through app layer.",
            faults=[Fault(target_component_id=cid, fault_type=FaultType.LATENCY_SPIKE,
                          parameters={"multiplier": 10})],
            traffic_multiplier=3.0,
        ))

    # =========================================================================
    # CATEGORY 25: Rolling restart failure
    # =========================================================================
    if len(app) >= 2:
        # Model a realistic rolling deployment with maxUnavailable strategy.
        # Kubernetes default maxUnavailable is 25%, so we fault at most 25% of
        # app servers (minimum 1, always keep at least one running).
        max_unavailable = max(1, len(app) // 4)
        batch = app[:min(max_unavailable, len(app) - 1)]
        scenarios.append(Scenario(
            id="rolling-restart-fail", name="Rolling restart failure",
            description=f"Rolling deployment: {len(batch)}/{len(app)} app servers down simultaneously (maxUnavailable={max_unavailable})",
            faults=[Fault(target_component_id=c, fault_type=FaultType.COMPONENT_DOWN,
                          parameters={"cause": "rolling_restart"}) for c in batch],
        ))

    # =========================================================================
    # CATEGORY 26: Downstream external API failure (if external_api components exist)
    # =========================================================================
    external = [cid for cid, c in (components or {}).items()
                if hasattr(c, 'type') and c.type.value == "external_api"]
    for cid in external:
        scenarios.append(Scenario(
            id=f"external-timeout-{cid}", name=f"External API timeout: {cid}",
            description=f"External dependency {cid} stops responding, blocking all calling services",
            faults=[Fault(target_component_id=cid, fault_type=FaultType.LATENCY_SPIKE,
                          parameters={"cause": "external_api_timeout", "multiplier": 100})],
        ))
        scenarios.append(Scenario(
            id=f"external-down-{cid}", name=f"External API down: {cid}",
            description=f"External dependency {cid} returns errors for all requests",
            faults=[Fault(target_component_id=cid, fault_type=FaultType.COMPONENT_DOWN,
                          parameters={"cause": "external_api_failure"})],
        ))

    # =========================================================================
    # CATEGORY 27: Network partition between tiers
    # =========================================================================
    # App servers can't reach DB
    if app and db:
        scenarios.append(Scenario(
            id="partition-app-db", name="Network partition: App <-> DB",
            description="Network partition between application tier and database tier",
            faults=[Fault(target_component_id=d, fault_type=FaultType.NETWORK_PARTITION,
                          parameters={"cause": "inter_tier_partition"}) for d in db],
        ))
    # App servers can't reach cache
    if app and cache:
        scenarios.append(Scenario(
            id="partition-app-cache", name="Network partition: App <-> Cache",
            description="Network partition between application tier and cache tier",
            faults=[Fault(target_component_id=c, fault_type=FaultType.NETWORK_PARTITION,
                          parameters={"cause": "inter_tier_partition"}) for c in cache],
        ))
    # LB can't reach app servers
    if lb and app:
        # When multiple LBs exist (e.g. ALB + NLB), create per-LB partition
        # scenarios.  A partition that isolates only one LB is lower severity
        # because the other LB may still route traffic (redundant path).
        if len(lb) > 1 and components:
            for lb_id in lb:
                comp = components.get(lb_id)
                lb_name = comp.name if comp else lb_id
                scenarios.append(Scenario(
                    id=f"partition-{lb_id}-app",
                    name=f"Network partition: {lb_name} <-> App",
                    description=f"Network partition isolating {lb_name} from application tier",
                    faults=[Fault(target_component_id=lb_id,
                                  fault_type=FaultType.COMPONENT_DOWN,
                                  parameters={"cause": "lb_app_partition"})],
                ))
        # Full partition: ALL load balancers lose connectivity to app tier
        scenarios.append(Scenario(
            id="partition-lb-app", name="Network partition: LB <-> App",
            description="Network partition between all load balancers and application tier",
            faults=[Fault(target_component_id=a, fault_type=FaultType.NETWORK_PARTITION,
                          parameters={"cause": "inter_tier_partition"}) for a in app],
        ))

    # =========================================================================
    # CATEGORY 28: Sustained resource degradation (multiple resources stressed)
    # =========================================================================
    for cid in app:
        scenarios.append(Scenario(
            id=f"resource-exhaustion-{cid}",
            name=f"Full resource exhaustion: {cid}",
            description=f"CPU saturated + memory near limit + disk filling on {cid}. Everything failing at once.",
            faults=[
                Fault(target_component_id=cid, fault_type=FaultType.CPU_SATURATION),
                Fault(target_component_id=cid, fault_type=FaultType.MEMORY_EXHAUSTION),
            ],
        ))

    # =========================================================================
    # CATEGORY 29: Cascading timeout scenarios
    # =========================================================================
    if components:
        for comp_id, comp in components.items():
            if comp.capacity.timeout_seconds > 0:
                scenarios.append(Scenario(
                    id=f"cascading-timeout-{comp_id}",
                    name=f"Cascading timeout from {comp_id}",
                    description=f"Slow {comp_id} causes upstream timeout cascades",
                    faults=[Fault(target_component_id=comp_id, fault_type=FaultType.LATENCY_SPIKE,
                                  parameters={"multiplier": 20})],
                ))

    # =========================================================================
    # CATEGORY 30: Sustained resource degradation
    # =========================================================================
    for cid in app:
        scenarios.append(Scenario(
            id=f"sustained-degradation-{cid}",
            name=f"Sustained degradation: {cid}",
            description=f"Multiple resources stressed simultaneously on {cid}",
            faults=[
                Fault(target_component_id=cid, fault_type=FaultType.CPU_SATURATION, severity=0.8),
                Fault(target_component_id=cid, fault_type=FaultType.MEMORY_EXHAUSTION, severity=0.7),
            ],
        ))

    # =========================================================================
    # CATEGORY 31: Failover testing
    # =========================================================================
    # If DB has replicas, test primary failure
    if components:
        for cid in db:
            comp = components.get(cid)
            if comp and comp.replicas > 1:
                scenarios.append(Scenario(
                    id=f"primary-failover-{cid}", name=f"Primary failover: {cid}",
                    description=f"Primary {cid} fails, replica must promote. Tests failover time and data consistency.",
                    faults=[Fault(target_component_id=cid, fault_type=FaultType.COMPONENT_DOWN,
                                  parameters={"cause": "primary_failover"})],
                ))

    # =========================================================================
    # CATEGORY 32: Black Friday / flash sale simulation
    # =========================================================================
    if component_ids:
        scenarios.append(Scenario(
            id="black-friday", name="Black Friday simulation (10x + cache pressure)",
            description="Flash sale: 10x traffic + cache eviction storm from new access patterns",
            faults=[Fault(target_component_id=c, fault_type=FaultType.MEMORY_EXHAUSTION,
                          parameters={"cause": "cache_pressure"}) for c in cache],
            traffic_multiplier=10.0,
        ))

    return scenarios


def generate_dynamic_scenarios(
    component_ids: list[str],
    components: dict | None = None,
) -> list[DynamicScenario]:
    """Generate dynamic chaos scenarios with time-varying traffic patterns.

    Unlike ``generate_default_scenarios`` which uses static traffic multipliers,
    these scenarios pair faults with realistic ``TrafficPattern`` objects that
    produce time-varying load curves (DDoS ramps, flash crowds, diurnal cycles,
    etc.).  They are intended for use with ``DynamicSimulationEngine``.
    """
    from faultray.simulator.traffic import (
        create_ddos_volumetric,
        create_ddos_slowloris,
        create_flash_crowd,
        create_viral_event,
        create_diurnal,
        TrafficPattern,
        TrafficPatternType,
    )

    scenarios: list[DynamicScenario] = []
    cats = _categorize(components, component_ids)

    db = cats["databases"]
    cache = cats["caches"]
    app = cats["app_servers"] + cats["web_servers"]
    lb = cats["load_balancers"]

    # =========================================================================
    # 1. DDoS Volumetric — 10x peak, 300s, all components
    # =========================================================================
    scenarios.append(DynamicScenario(
        id="dynamic-ddos-volumetric",
        name="DDoS Volumetric (dynamic)",
        description=(
            "Volumetric DDoS attack: traffic ramps to 10x in 10s then sustains "
            "with jitter.  Tests auto-scaling triggers and rate-limiting."
        ),
        faults=[],
        traffic_pattern=create_ddos_volumetric(peak=10.0, duration=300),
        duration_seconds=300,
    ))

    # =========================================================================
    # 2. DDoS Slowloris — 5x peak, 300s, targeting app servers + LBs
    # =========================================================================
    slowloris_targets = app + lb if (app or lb) else component_ids
    slowloris_pattern = create_ddos_slowloris(peak=5.0, duration=300)
    slowloris_pattern = slowloris_pattern.model_copy(
        update={"affected_components": slowloris_targets},
    )
    scenarios.append(DynamicScenario(
        id="dynamic-ddos-slowloris",
        name="DDoS Slowloris (dynamic)",
        description=(
            "Slowloris attack: connections climb linearly to 5x over 300s, "
            "targeting app servers and load balancers.  Exhausts connection pools."
        ),
        faults=[],
        traffic_pattern=slowloris_pattern,
        duration_seconds=300,
    ))

    # =========================================================================
    # 3. Flash Crowd — 8x peak, 30s ramp, 300s (viral tweet scenario)
    # =========================================================================
    scenarios.append(DynamicScenario(
        id="dynamic-flash-crowd",
        name="Flash Crowd: viral tweet (dynamic)",
        description=(
            "Viral tweet drives exponential traffic ramp to 8x in 30s, then "
            "slow linear decay.  Tests burst absorption and queue back-pressure."
        ),
        faults=[],
        traffic_pattern=create_flash_crowd(peak=8.0, ramp=30, duration=300),
        duration_seconds=300,
    ))

    # =========================================================================
    # 4. Viral Event + DB failure — flash crowd + primary DB down
    # =========================================================================
    if db:
        scenarios.append(DynamicScenario(
            id="dynamic-viral-db-failure",
            name="Viral event + DB failure (dynamic)",
            description=(
                "Viral event drives 15x traffic surge while the primary database "
                "goes down.  Tests failover under extreme read/write pressure."
            ),
            faults=[Fault(
                target_component_id=db[0],
                fault_type=FaultType.COMPONENT_DOWN,
            )],
            traffic_pattern=create_viral_event(peak=15.0, duration=300),
            duration_seconds=300,
        ))

    # =========================================================================
    # 5. Diurnal cycle with fault — diurnal 3x + cache failure mid-cycle
    # =========================================================================
    if cache:
        scenarios.append(DynamicScenario(
            id="dynamic-diurnal-cache-failure",
            name="Diurnal cycle + cache failure (dynamic)",
            description=(
                "Normal diurnal traffic (3x peak at midpoint) combined with "
                "cache failure mid-cycle.  Simulates a cache node dying during "
                "peak business hours."
            ),
            faults=[Fault(
                target_component_id=cache[0],
                fault_type=FaultType.COMPONENT_DOWN,
            )],
            traffic_pattern=create_diurnal(peak=3.0, duration=300),
            duration_seconds=300,
        ))

    # =========================================================================
    # 6. Spike during deployment — spike traffic + app server down
    # =========================================================================
    if app:
        spike_pattern = TrafficPattern(
            pattern_type=TrafficPatternType.SPIKE,
            peak_multiplier=5.0,
            duration_seconds=300,
            ramp_seconds=60,
            sustain_seconds=120,
            description="Spike: instant 5x at t=60, sustain 120s",
        )
        scenarios.append(DynamicScenario(
            id="dynamic-spike-during-deploy",
            name="Spike during deployment (dynamic)",
            description=(
                "Traffic spikes to 5x at t=60 and sustains for 120s while an "
                "app server is down due to a bad deployment.  Tests graceful "
                "degradation with reduced capacity."
            ),
            faults=[Fault(
                target_component_id=app[0],
                fault_type=FaultType.COMPONENT_DOWN,
                parameters={"cause": "bad_deployment"},
            )],
            traffic_pattern=spike_pattern,
            duration_seconds=300,
        ))

    # =========================================================================
    # 7. DDoS + network partition — volumetric DDoS + network partition
    # =========================================================================
    if component_ids:
        key_component = (db[0] if db else (app[0] if app else component_ids[0]))
        scenarios.append(DynamicScenario(
            id="dynamic-ddos-net-partition",
            name="DDoS + network partition (dynamic)",
            description=(
                f"Volumetric DDoS (10x) coincides with a network partition "
                f"isolating {key_component}.  Tests resilience when both external "
                f"pressure and internal connectivity fail simultaneously."
            ),
            faults=[Fault(
                target_component_id=key_component,
                fault_type=FaultType.NETWORK_PARTITION,
            )],
            traffic_pattern=create_ddos_volumetric(peak=10.0, duration=300),
            duration_seconds=300,
        ))

    # =========================================================================
    # 8. Sustained high load — wave 5x peak, 30s period + memory exhaustion
    # =========================================================================
    if app:
        wave_pattern = TrafficPattern(
            pattern_type=TrafficPatternType.WAVE,
            peak_multiplier=5.0,
            duration_seconds=300,
            wave_period_seconds=30,
            description="Wave: 5x peak, 30s period",
        )
        scenarios.append(DynamicScenario(
            id="dynamic-sustained-high-load",
            name="Sustained high load + memory exhaustion (dynamic)",
            description=(
                "Oscillating traffic (5x peak, 30s period) combined with gradual "
                "memory exhaustion on an app server.  Tests whether the system "
                "survives prolonged pressure without OOM-killing critical processes."
            ),
            faults=[Fault(
                target_component_id=app[0],
                fault_type=FaultType.MEMORY_EXHAUSTION,
                parameters={"cause": "gradual_leak"},
            )],
            traffic_pattern=wave_pattern,
            duration_seconds=300,
        ))

    # =========================================================================
    # 9. Flash crowd + cache stampede — flash crowd 15x + all caches down
    # =========================================================================
    if cache:
        scenarios.append(DynamicScenario(
            id="dynamic-flash-cache-stampede",
            name="Flash crowd + cache stampede (dynamic)",
            description=(
                "Extreme flash crowd (15x) hits while all cache nodes are down.  "
                "Every request falls through to the database tier, creating a "
                "thundering-herd / cache-stampede scenario."
            ),
            faults=[
                Fault(
                    target_component_id=c,
                    fault_type=FaultType.COMPONENT_DOWN,
                )
                for c in cache
            ],
            traffic_pattern=create_flash_crowd(peak=15.0, ramp=30, duration=300),
            duration_seconds=300,
        ))

    return scenarios
