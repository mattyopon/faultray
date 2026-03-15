"""Incident correlation engine — find hidden relationships between failures.

Analyzes infrastructure topology and failure patterns to identify
correlated incidents that share root causes, common dependencies,
or temporal proximity. Enables faster root cause analysis by
surfacing connections that humans might miss.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from enum import Enum

from infrasim.model.components import Component, HealthStatus
from infrasim.model.graph import InfraGraph


class CorrelationType(str, Enum):
    """Types of incident correlation."""

    SHARED_DEPENDENCY = "shared_dependency"
    SAME_TYPE = "same_type"
    CASCADE_CHAIN = "cascade_chain"
    RESOURCE_CONTENTION = "resource_contention"
    BLAST_RADIUS = "blast_radius"
    CONFIGURATION_DRIFT = "configuration_drift"


class CorrelationStrength(str, Enum):
    """Strength of correlation between incidents."""

    STRONG = "strong"      # >80% confidence
    MODERATE = "moderate"  # 50-80% confidence
    WEAK = "weak"          # 20-50% confidence
    NONE = "none"          # <20% confidence


@dataclass
class IncidentSignal:
    """A signal from a component that may indicate an incident."""

    component_id: str
    component_name: str
    signal_type: str  # "health_degraded", "resource_pressure", "capacity_warning"
    severity: float  # 0-1
    details: str


@dataclass
class CorrelationLink:
    """A correlation between two incident signals."""

    signal_a: IncidentSignal
    signal_b: IncidentSignal
    correlation_type: CorrelationType
    strength: CorrelationStrength
    confidence: float  # 0-1
    explanation: str
    shared_factor: str  # What they share (dependency name, resource type, etc.)


@dataclass
class CorrelationCluster:
    """A group of correlated incidents sharing a root cause."""

    cluster_id: str
    signals: list[IncidentSignal]
    links: list[CorrelationLink]
    probable_root_cause: str
    affected_components: list[str]
    severity: float  # 0-1 (worst signal severity)
    recommended_investigation: list[str]


@dataclass
class CorrelationReport:
    """Full incident correlation analysis."""

    signals: list[IncidentSignal]
    links: list[CorrelationLink]
    clusters: list[CorrelationCluster]
    total_signals: int
    total_correlations: int
    total_clusters: int
    highest_severity_cluster: str
    root_cause_candidates: list[str]
    summary: str


class IncidentCorrelationEngine:
    """Analyze infrastructure for correlated incidents."""

    def __init__(self, graph: InfraGraph) -> None:
        self._graph = graph

    def analyze(self) -> CorrelationReport:
        """Run full correlation analysis."""
        # Step 1: Collect signals
        signals = self._collect_signals()

        if not signals:
            return CorrelationReport(
                signals=[],
                links=[],
                clusters=[],
                total_signals=0,
                total_correlations=0,
                total_clusters=0,
                highest_severity_cluster="",
                root_cause_candidates=[],
                summary="No incident signals detected. Infrastructure appears healthy.",
            )

        # Step 2: Find correlations
        links = self._find_correlations(signals)

        # Step 3: Cluster correlated signals
        clusters = self._build_clusters(signals, links)

        # Step 4: Generate report
        root_causes = []
        for cluster in clusters:
            if cluster.probable_root_cause:
                root_causes.append(cluster.probable_root_cause)

        highest = ""
        if clusters:
            worst = max(clusters, key=lambda c: c.severity)
            highest = worst.cluster_id

        summary = self._generate_summary(signals, links, clusters)

        return CorrelationReport(
            signals=signals,
            links=links,
            clusters=clusters,
            total_signals=len(signals),
            total_correlations=len(links),
            total_clusters=len(clusters),
            highest_severity_cluster=highest,
            root_cause_candidates=root_causes,
            summary=summary,
        )

    def _collect_signals(self) -> list[IncidentSignal]:
        """Collect incident signals from all components."""
        signals: list[IncidentSignal] = []

        for comp in self._graph.components.values():
            signals.extend(self._component_signals(comp))

        return signals

    def _component_signals(self, comp: Component) -> list[IncidentSignal]:
        """Extract incident signals from a single component."""
        signals: list[IncidentSignal] = []

        # Health-based signals
        if comp.health == HealthStatus.DEGRADED:
            signals.append(IncidentSignal(
                component_id=comp.id,
                component_name=comp.name,
                signal_type="health_degraded",
                severity=0.5,
                details=f"{comp.name} is in DEGRADED state",
            ))
        elif comp.health == HealthStatus.OVERLOADED:
            signals.append(IncidentSignal(
                component_id=comp.id,
                component_name=comp.name,
                signal_type="health_overloaded",
                severity=0.8,
                details=f"{comp.name} is OVERLOADED",
            ))
        elif comp.health == HealthStatus.DOWN:
            signals.append(IncidentSignal(
                component_id=comp.id,
                component_name=comp.name,
                signal_type="health_down",
                severity=1.0,
                details=f"{comp.name} is DOWN",
            ))

        # Resource pressure signals
        if comp.metrics.cpu_percent > 80:
            signals.append(IncidentSignal(
                component_id=comp.id,
                component_name=comp.name,
                signal_type="resource_cpu_high",
                severity=min(1.0, comp.metrics.cpu_percent / 100),
                details=f"{comp.name} CPU at {comp.metrics.cpu_percent}%",
            ))

        if comp.metrics.memory_percent > 80:
            signals.append(IncidentSignal(
                component_id=comp.id,
                component_name=comp.name,
                signal_type="resource_memory_high",
                severity=min(1.0, comp.metrics.memory_percent / 100),
                details=f"{comp.name} memory at {comp.metrics.memory_percent}%",
            ))

        if comp.metrics.disk_percent > 80:
            signals.append(IncidentSignal(
                component_id=comp.id,
                component_name=comp.name,
                signal_type="resource_disk_high",
                severity=min(1.0, comp.metrics.disk_percent / 100),
                details=f"{comp.name} disk at {comp.metrics.disk_percent}%",
            ))

        # Capacity signals
        if comp.capacity.max_connections > 0:
            ratio = comp.metrics.network_connections / comp.capacity.max_connections
            if ratio > 0.8:
                signals.append(IncidentSignal(
                    component_id=comp.id,
                    component_name=comp.name,
                    signal_type="capacity_connections",
                    severity=min(1.0, ratio),
                    details=f"{comp.name} connections at {ratio * 100:.0f}% capacity",
                ))

        return signals

    def _find_correlations(self, signals: list[IncidentSignal]) -> list[CorrelationLink]:
        """Find correlations between incident signals."""
        links: list[CorrelationLink] = []

        for i, sig_a in enumerate(signals):
            for sig_b in signals[i + 1:]:
                if sig_a.component_id == sig_b.component_id:
                    continue  # Skip self-correlation

                link = self._check_correlation(sig_a, sig_b)
                if link:
                    links.append(link)

        return links

    def _check_correlation(
        self, sig_a: IncidentSignal, sig_b: IncidentSignal
    ) -> CorrelationLink | None:
        """Check if two signals are correlated."""
        comp_a = self._graph.get_component(sig_a.component_id)
        comp_b = self._graph.get_component(sig_b.component_id)

        if not comp_a or not comp_b:
            return None

        # Check shared dependency
        deps_a = {d.id for d in self._graph.get_dependencies(comp_a.id)}
        deps_b = {d.id for d in self._graph.get_dependencies(comp_b.id)}
        shared_deps = deps_a & deps_b
        if shared_deps:
            shared_name = ", ".join(shared_deps)
            return CorrelationLink(
                signal_a=sig_a,
                signal_b=sig_b,
                correlation_type=CorrelationType.SHARED_DEPENDENCY,
                strength=CorrelationStrength.STRONG,
                confidence=0.85,
                explanation=f"{sig_a.component_name} and {sig_b.component_name} share dependency: {shared_name}",
                shared_factor=shared_name,
            )

        # Check cascade chain (A depends on B or B depends on A)
        if comp_b.id in deps_a:
            return CorrelationLink(
                signal_a=sig_a,
                signal_b=sig_b,
                correlation_type=CorrelationType.CASCADE_CHAIN,
                strength=CorrelationStrength.STRONG,
                confidence=0.9,
                explanation=f"{sig_a.component_name} depends on {sig_b.component_name} — likely cascade",
                shared_factor=f"dependency: {comp_a.id} → {comp_b.id}",
            )
        if comp_a.id in deps_b:
            return CorrelationLink(
                signal_a=sig_a,
                signal_b=sig_b,
                correlation_type=CorrelationType.CASCADE_CHAIN,
                strength=CorrelationStrength.STRONG,
                confidence=0.9,
                explanation=f"{sig_b.component_name} depends on {sig_a.component_name} — likely cascade",
                shared_factor=f"dependency: {comp_b.id} → {comp_a.id}",
            )

        # Check same type (potential common issue)
        if comp_a.type == comp_b.type:
            return CorrelationLink(
                signal_a=sig_a,
                signal_b=sig_b,
                correlation_type=CorrelationType.SAME_TYPE,
                strength=CorrelationStrength.MODERATE,
                confidence=0.6,
                explanation=f"Both are {comp_a.type.value} — may share common vulnerability",
                shared_factor=comp_a.type.value,
            )

        # Check resource contention (both have high resource usage)
        resource_types = {"resource_cpu_high", "resource_memory_high", "resource_disk_high"}
        if sig_a.signal_type in resource_types and sig_b.signal_type in resource_types:
            return CorrelationLink(
                signal_a=sig_a,
                signal_b=sig_b,
                correlation_type=CorrelationType.RESOURCE_CONTENTION,
                strength=CorrelationStrength.MODERATE,
                confidence=0.55,
                explanation="Both components under resource pressure — possible contention",
                shared_factor="resource_pressure",
            )

        return None

    def _build_clusters(
        self,
        signals: list[IncidentSignal],
        links: list[CorrelationLink],
    ) -> list[CorrelationCluster]:
        """Group correlated signals into clusters."""
        # Build adjacency from links
        adjacency: dict[str, set[str]] = defaultdict(set)
        for link in links:
            adjacency[link.signal_a.component_id].add(link.signal_b.component_id)
            adjacency[link.signal_b.component_id].add(link.signal_a.component_id)

        # Find connected components using BFS
        visited: set[str] = set()
        clusters: list[CorrelationCluster] = []
        cluster_counter = 0

        signal_map: dict[str, list[IncidentSignal]] = defaultdict(list)
        for sig in signals:
            signal_map[sig.component_id].append(sig)

        # Process linked components
        for comp_id in adjacency:
            if comp_id in visited:
                continue

            # BFS to find cluster
            queue = [comp_id]
            cluster_components: set[str] = set()
            while queue:
                current = queue.pop(0)
                if current in visited:
                    continue
                visited.add(current)
                cluster_components.add(current)
                for neighbor in adjacency.get(current, set()):
                    if neighbor not in visited:
                        queue.append(neighbor)

            if not cluster_components:
                continue

            cluster_counter += 1
            cluster_signals = []
            for cid in cluster_components:
                cluster_signals.extend(signal_map.get(cid, []))

            cluster_links = [
                link for link in links
                if link.signal_a.component_id in cluster_components
                and link.signal_b.component_id in cluster_components
            ]

            severity = max((s.severity for s in cluster_signals), default=0.0)
            root_cause = self._identify_root_cause(cluster_signals, cluster_links)
            investigation = self._recommend_investigation(cluster_signals, cluster_links)

            clusters.append(CorrelationCluster(
                cluster_id=f"CL-{cluster_counter:03d}",
                signals=cluster_signals,
                links=cluster_links,
                probable_root_cause=root_cause,
                affected_components=list(cluster_components),
                severity=severity,
                recommended_investigation=investigation,
            ))

        # Add uncorrelated signals as individual clusters
        for sig in signals:
            if sig.component_id not in visited:
                visited.add(sig.component_id)
                cluster_counter += 1
                clusters.append(CorrelationCluster(
                    cluster_id=f"CL-{cluster_counter:03d}",
                    signals=[sig],
                    links=[],
                    probable_root_cause=f"Isolated issue on {sig.component_name}: {sig.signal_type}",
                    affected_components=[sig.component_id],
                    severity=sig.severity,
                    recommended_investigation=[
                        f"Investigate {sig.component_name} {sig.signal_type}"
                    ],
                ))

        # Sort by severity descending
        clusters.sort(key=lambda c: c.severity, reverse=True)
        return clusters

    def _identify_root_cause(
        self,
        signals: list[IncidentSignal],
        links: list[CorrelationLink],
    ) -> str:
        """Identify the most likely root cause for a cluster."""
        # Check for cascade chain → upstream is root cause
        for link in links:
            if link.correlation_type == CorrelationType.CASCADE_CHAIN:
                return f"Cascade from {link.shared_factor}"

        # Check for shared dependency → dependency is root cause
        for link in links:
            if link.correlation_type == CorrelationType.SHARED_DEPENDENCY:
                return f"Shared dependency issue: {link.shared_factor}"

        # Check for resource contention
        for link in links:
            if link.correlation_type == CorrelationType.RESOURCE_CONTENTION:
                return "Resource contention across components"

        # Check for same type → common vulnerability
        for link in links:
            if link.correlation_type == CorrelationType.SAME_TYPE:
                return f"Common vulnerability in {link.shared_factor} components"

        # Fallback
        if signals:
            worst = max(signals, key=lambda s: s.severity)
            return f"Primary issue: {worst.component_name} ({worst.signal_type})"

        return "Unknown"

    def _recommend_investigation(
        self,
        signals: list[IncidentSignal],
        links: list[CorrelationLink],
    ) -> list[str]:
        """Generate investigation recommendations."""
        recs: list[str] = []

        # Group by signal type
        types = {s.signal_type for s in signals}

        if "health_down" in types:
            recs.append("Check component logs for crash/OOM errors")
        if "health_overloaded" in types:
            recs.append("Review load patterns and autoscaling configuration")
        if "resource_cpu_high" in types:
            recs.append("Profile CPU-intensive operations, check for infinite loops")
        if "resource_memory_high" in types:
            recs.append("Check for memory leaks, review garbage collection")
        if "resource_disk_high" in types:
            recs.append("Review log rotation, clean up temporary files")
        if "capacity_connections" in types:
            recs.append("Check for connection leaks, review pool configuration")

        for link in links:
            if link.correlation_type == CorrelationType.CASCADE_CHAIN:
                recs.append(f"Investigate upstream dependency: {link.shared_factor}")
                break
            if link.correlation_type == CorrelationType.SHARED_DEPENDENCY:
                recs.append(f"Check shared dependency health: {link.shared_factor}")
                break

        if not recs:
            recs.append("Review component metrics and recent changes")

        return recs[:5]

    def _generate_summary(
        self,
        signals: list[IncidentSignal],
        links: list[CorrelationLink],
        clusters: list[CorrelationCluster],
    ) -> str:
        """Generate a human-readable summary."""
        if not signals:
            return "No incident signals detected."

        parts = [f"{len(signals)} incident signal{'s' if len(signals) > 1 else ''} detected"]

        if links:
            parts.append(f"{len(links)} correlation{'s' if len(links) > 1 else ''} found")

        if clusters:
            parts.append(f"{len(clusters)} cluster{'s' if len(clusters) > 1 else ''} identified")

        critical = sum(1 for s in signals if s.severity >= 0.8)
        if critical:
            parts.append(f"{critical} CRITICAL severity")

        return ". ".join(parts) + "."
