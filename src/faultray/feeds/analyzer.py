# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Business Source License 1.1. See LICENSE file for details.

"""Analyze security news articles and extract infrastructure incident patterns.

Converts real-world incident reports into chaos engineering scenarios.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field

from faultray.feeds.fetcher import FeedArticle
from faultray.simulator.scenarios import Fault, FaultType, Scenario


# ---------------------------------------------------------------------------
# Incident pattern definitions
# ---------------------------------------------------------------------------

@dataclass
class IncidentPattern:
    """A pattern that maps keywords in news articles to chaos scenarios."""

    id: str
    name: str
    description_template: str
    keywords: list[str]  # Any of these must match
    negative_keywords: list[str] = field(default_factory=list)  # Must NOT match
    fault_types: list[FaultType] = field(default_factory=list)
    traffic_multiplier: float = 1.0
    severity: float = 1.0
    min_keyword_matches: int = 1  # How many keywords must match
    component_types: list[str] = field(default_factory=list)  # Target component types


# Master pattern library - maps real-world incidents to simulations
INCIDENT_PATTERNS: list[IncidentPattern] = [
    # --- DDoS / Traffic floods ---
    IncidentPattern(
        id="ddos_volumetric",
        name="DDoS volumetric attack",
        description_template="Volumetric DDoS attack pattern observed: {title}",
        keywords=["ddos", "denial.of.service", "traffic flood", "volumetric attack",
                  "amplification attack", "udp flood", "syn flood", "http flood"],
        fault_types=[FaultType.TRAFFIC_SPIKE],
        traffic_multiplier=10.0,
        severity=1.0,
        component_types=["load_balancer", "web_server", "app_server"],
    ),
    IncidentPattern(
        id="ddos_application",
        name="Application-layer DDoS",
        description_template="Application-layer DDoS (L7) pattern: {title}",
        keywords=["layer 7 ddos", "application.layer attack", "slowloris",
                  "http slow", "request flood", "api abuse"],
        fault_types=[FaultType.CONNECTION_POOL_EXHAUSTION, FaultType.CPU_SATURATION],
        traffic_multiplier=5.0,
        severity=1.0,
        component_types=["app_server", "web_server"],
    ),

    # --- Outages / Crashes ---
    IncidentPattern(
        id="cloud_outage",
        name="Cloud provider outage",
        description_template="Cloud provider outage scenario: {title}",
        keywords=["aws outage", "azure outage", "gcp outage", "cloud outage",
                  "cloud downtime", "region.* down", "availability zone.* fail",
                  "service disruption"],
        fault_types=[FaultType.COMPONENT_DOWN, FaultType.NETWORK_PARTITION],
        severity=1.0,
    ),
    IncidentPattern(
        id="dns_outage",
        name="DNS infrastructure failure",
        description_template="DNS failure scenario: {title}",
        keywords=["dns outage", "dns failure", "dns hijack", "dns poison",
                  "domain.* down", "name.server.* fail", "dns amplification"],
        fault_types=[FaultType.COMPONENT_DOWN, FaultType.NETWORK_PARTITION],
        severity=1.0,
        component_types=["dns"],
    ),

    # --- Database incidents ---
    IncidentPattern(
        id="db_corruption",
        name="Database corruption / data loss",
        description_template="Database failure pattern: {title}",
        keywords=["database corrup", "data loss", "data breach.*database",
                  "db crash", "replication.* fail", "replication lag",
                  "database.* outage", "rds.* fail", "aurora.* issue"],
        fault_types=[FaultType.COMPONENT_DOWN, FaultType.DISK_FULL],
        severity=1.0,
        component_types=["database"],
    ),
    IncidentPattern(
        id="db_connection_storm",
        name="Database connection storm",
        description_template="DB connection exhaustion: {title}",
        keywords=["connection.* exhaust", "connection.* limit", "too many connection",
                  "connection pool", "connection storm", "max_connections",
                  "database.* overload"],
        fault_types=[FaultType.CONNECTION_POOL_EXHAUSTION],
        severity=1.0,
        component_types=["database"],
    ),

    # --- Memory / OOM ---
    IncidentPattern(
        id="memory_leak_incident",
        name="Memory leak causing OOM",
        description_template="Memory exhaustion incident: {title}",
        keywords=["memory leak", "out.of.memory", "oom kill", "oom.* crash",
                  "heap.* exhaust", "memory.* exhaust", "memory.* spike",
                  "java.* heap", "container.* memory"],
        fault_types=[FaultType.MEMORY_EXHAUSTION],
        severity=1.0,
    ),

    # --- Certificate / TLS ---
    IncidentPattern(
        id="tls_cert_incident",
        name="TLS certificate failure",
        description_template="Certificate/TLS failure: {title}",
        keywords=["certificate.* expir", "ssl.* expir", "tls.* expir",
                  "certificate.* revok", "cert.* outage", "https.* fail",
                  "certificate.* misconfig", "ssl.* vulnerab"],
        fault_types=[FaultType.COMPONENT_DOWN],
        severity=1.0,
        component_types=["load_balancer", "web_server"],
    ),

    # --- Network ---
    IncidentPattern(
        id="network_partition_incident",
        name="Network partition / split brain",
        description_template="Network partition scenario: {title}",
        keywords=["network partition", "split.brain", "network.* segment",
                  "bgp.* hijack", "bgp.* leak", "routing.* fail",
                  "connectivity.* loss", "inter.region.* fail",
                  "submarine cable", "fiber cut"],
        fault_types=[FaultType.NETWORK_PARTITION],
        severity=1.0,
    ),

    # --- Storage / Disk ---
    IncidentPattern(
        id="storage_incident",
        name="Storage failure / disk full",
        description_template="Storage failure pattern: {title}",
        keywords=["disk full", "storage.* fail", "ebs.* fail", "s3.* outage",
                  "storage.* corrupt", "disk.* error", "io.* error",
                  "filesystem.* full", "inode.* exhaust"],
        fault_types=[FaultType.DISK_FULL],
        severity=1.0,
        component_types=["database", "storage"],
    ),

    # --- Cache ---
    IncidentPattern(
        id="cache_incident",
        name="Cache failure / stampede",
        description_template="Cache failure scenario: {title}",
        keywords=["redis.* crash", "redis.* fail", "memcache.* fail",
                  "cache.* stampede", "cache.* thunder", "elasticache.* fail",
                  "cache.* evict", "cache.* corrupt"],
        fault_types=[FaultType.COMPONENT_DOWN, FaultType.MEMORY_EXHAUSTION],
        severity=1.0,
        component_types=["cache"],
    ),

    # --- Queue / Message broker ---
    IncidentPattern(
        id="queue_incident",
        name="Message queue failure",
        description_template="Queue/broker failure: {title}",
        keywords=["kafka.* fail", "kafka.* outage", "rabbitmq.* fail",
                  "sqs.* fail", "message.* queue.* fail", "broker.* crash",
                  "queue.* backlog", "message.* lost", "dead.letter"],
        fault_types=[FaultType.COMPONENT_DOWN],
        severity=1.0,
        component_types=["queue"],
    ),

    # --- CPU / Compute ---
    IncidentPattern(
        id="cpu_crypto_mining",
        name="CPU exhaustion (cryptomining / abuse)",
        description_template="Compute resource abuse: {title}",
        keywords=["cryptomin", "crypto.?jack", "cpu.* spike", "cpu.* exhaust",
                  "compute.* abuse", "resource.* hijack", "container.* escape",
                  "cpu.* 100"],
        fault_types=[FaultType.CPU_SATURATION],
        severity=1.0,
    ),

    # --- Supply chain / Dependency ---
    IncidentPattern(
        id="supply_chain",
        name="Supply chain / dependency failure",
        description_template="Third-party dependency failure: {title}",
        keywords=["supply.chain", "dependency.* vuln", "npm.* malicious",
                  "pypi.* malicious", "typosquat", "package.* comprom",
                  "third.party.* fail", "api.* outage", "upstream.* fail",
                  "vendor.* outage", "saas.* outage"],
        fault_types=[FaultType.COMPONENT_DOWN, FaultType.LATENCY_SPIKE],
        severity=1.0,
        component_types=["external_api"],
    ),

    # --- Ransomware ---
    IncidentPattern(
        id="ransomware",
        name="Ransomware / encryption attack",
        description_template="Ransomware impact simulation: {title}",
        keywords=["ransomware", "encrypt.*attack", "lockbit", "blackcat",
                  "conti.* ransomware", "data.* encrypt.*ransom",
                  "double.extortion"],
        fault_types=[FaultType.COMPONENT_DOWN, FaultType.DISK_FULL],
        severity=1.0,
    ),

    # --- Latency / Performance degradation ---
    IncidentPattern(
        id="latency_degradation",
        name="Latency / performance degradation",
        description_template="Performance degradation: {title}",
        keywords=["latency.* spike", "slow.*response", "timeout.*increase",
                  "performance.* degrad", "response.* time.*increase",
                  "p99.* latency", "tail.* latency"],
        fault_types=[FaultType.LATENCY_SPIKE],
        severity=0.8,
    ),

    # --- Container / Kubernetes ---
    IncidentPattern(
        id="k8s_incident",
        name="Kubernetes / container incident",
        description_template="Container orchestration failure: {title}",
        keywords=["kubernetes.* vuln", "k8s.* fail", "container.* escape",
                  "pod.* crash", "node.* drain", "kubelet.* fail",
                  "etcd.* fail", "control.plane.* fail", "ecs.* fail"],
        fault_types=[FaultType.COMPONENT_DOWN, FaultType.CPU_SATURATION],
        severity=1.0,
        component_types=["app_server"],
    ),

    # --- Cascading failure ---
    IncidentPattern(
        id="cascading_failure",
        name="Cascading failure / retry storm",
        description_template="Cascading failure pattern: {title}",
        keywords=["cascad.*fail", "retry.storm", "thundering.herd",
                  "circuit.break", "domino.* fail", "chain.*reaction",
                  "widespread.* outage"],
        fault_types=[FaultType.COMPONENT_DOWN, FaultType.LATENCY_SPIKE,
                     FaultType.CONNECTION_POOL_EXHAUSTION],
        traffic_multiplier=3.0,
        severity=1.0,
    ),

    # --- Configuration / Deployment ---
    IncidentPattern(
        id="bad_config_deploy",
        name="Bad configuration / deployment failure",
        description_template="Config/deploy failure: {title}",
        keywords=["misconfig", "bad.deploy", "rollback.*fail", "config.*error",
                  "deploy.*fail", "blue.green.*fail", "canary.*fail",
                  "feature.flag.*fail"],
        fault_types=[FaultType.COMPONENT_DOWN, FaultType.LATENCY_SPIKE],
        severity=0.8,
    ),
]


# ---------------------------------------------------------------------------
# Analysis engine
# ---------------------------------------------------------------------------

@dataclass
class AnalyzedIncident:
    """An article matched against an incident pattern."""

    article: FeedArticle
    pattern: IncidentPattern
    matched_keywords: list[str]
    confidence: float  # 0.0 - 1.0


def _match_keywords(text: str, keywords: list[str]) -> list[str]:
    """Find which keywords match in the text using regex."""
    matched = []
    for kw in keywords:
        # Support regex patterns in keywords (e.g., "redis.* fail")
        try:
            if re.search(kw, text, re.IGNORECASE):
                matched.append(kw)
        except re.error:
            # Fall back to literal match
            if kw.lower() in text.lower():
                matched.append(kw)
    return matched


def analyze_articles(articles: list[FeedArticle]) -> list[AnalyzedIncident]:
    """Analyze articles against incident patterns.

    Returns matched incidents sorted by confidence (highest first).
    """
    incidents: list[AnalyzedIncident] = []
    seen_ids: set[str] = set()

    for article in articles:
        text = article.full_text

        for pattern in INCIDENT_PATTERNS:
            # Check negative keywords first
            neg_matches = _match_keywords(text, pattern.negative_keywords)
            if neg_matches:
                continue

            # Check positive keywords
            matches = _match_keywords(text, pattern.keywords)
            if len(matches) < pattern.min_keyword_matches:
                continue

            # Calculate confidence based on match density
            confidence = min(1.0, len(matches) / max(3, len(pattern.keywords) * 0.3))

            # Deduplicate by article+pattern
            dedup_key = f"{article.link}:{pattern.id}"
            if dedup_key in seen_ids:
                continue
            seen_ids.add(dedup_key)

            incidents.append(AnalyzedIncident(
                article=article,
                pattern=pattern,
                matched_keywords=matches,
                confidence=confidence,
            ))

    incidents.sort(key=lambda i: i.confidence, reverse=True)
    return incidents


def _scenario_id(incident: AnalyzedIncident) -> str:
    """Generate a stable, unique scenario ID from an incident."""
    raw = f"{incident.pattern.id}:{incident.article.link}"
    return f"feed-{hashlib.sha256(raw.encode()).hexdigest()[:12]}"


def incidents_to_scenarios(
    incidents: list[AnalyzedIncident],
    component_ids: list[str],
    components: dict | None = None,
) -> list[Scenario]:
    """Convert analyzed incidents into runnable chaos scenarios.

    Maps incident patterns to the actual infrastructure components available
    in the user's model.
    """
    scenarios: list[Scenario] = []
    seen_ids: set[str] = set()

    # Categorize available components by type
    type_map: dict[str, list[str]] = {}
    if components:
        for cid, comp in components.items():
            ctype = comp.type.value if hasattr(comp.type, "value") else str(comp.type)
            type_map.setdefault(ctype, []).append(cid)

    for incident in incidents:
        pattern = incident.pattern
        sid = _scenario_id(incident)
        if sid in seen_ids:
            continue
        seen_ids.add(sid)

        # Determine target components
        if pattern.component_types and components:
            targets = []
            for ct in pattern.component_types:
                targets.extend(type_map.get(ct, []))
            if not targets:
                # Fall back to all components
                targets = component_ids
        else:
            targets = component_ids

        # Build faults
        faults: list[Fault] = []
        for fault_type in pattern.fault_types:
            for target_id in targets:
                faults.append(Fault(
                    target_component_id=target_id,
                    fault_type=fault_type,
                    severity=pattern.severity,
                ))

        if not faults:
            continue

        # Truncate article title for scenario name
        title = incident.article.title[:80]
        description = pattern.description_template.format(title=title)

        scenarios.append(Scenario(
            id=sid,
            name=f"[FEED] {pattern.name}",
            description=f"{description}\nSource: {incident.article.source_name} - {incident.article.link}",
            faults=faults,
            traffic_multiplier=pattern.traffic_multiplier,
        ))

    return scenarios
