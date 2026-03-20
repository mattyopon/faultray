# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Business Source License 1.1. See LICENSE file for details.

"""Network latency and reliability simulator.

Models realistic network conditions including latency degradation,
packet loss, DNS failures, and TLS handshake issues to predict
their cascading impact on service availability and response times.
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass
from enum import Enum

from faultray.model.components import ComponentType, HealthStatus
from faultray.model.graph import InfraGraph


class NetworkCondition(str, Enum):
    """Network condition states for simulation."""

    NORMAL = "normal"
    DEGRADED = "degraded"  # Higher latency
    CONGESTED = "congested"  # Packet loss + latency
    PARTITIONED = "partitioned"  # Network partition
    DNS_FAILURE = "dns_failure"
    TLS_FAILURE = "tls_failure"


@dataclass
class NetworkLink:
    """Represents a network link between two components."""

    source_id: str
    target_id: str
    base_latency_ms: float
    current_latency_ms: float
    packet_loss_rate: float  # 0-1.0
    condition: NetworkCondition
    is_healthy: bool


@dataclass
class NetworkSimulationResult:
    """Result of a network simulation run."""

    links: list[NetworkLink]
    total_links: int
    healthy_links: int
    degraded_links: int
    failed_links: int
    p50_latency_ms: float
    p95_latency_ms: float
    p99_latency_ms: float
    partition_detected: bool
    partition_groups: list[list[str]]  # Component groups that can't communicate
    overall_health: str  # "healthy", "degraded", "critical"
    recommendations: list[str]


@dataclass
class LatencyPrediction:
    """Predicted latency for a path between two components."""

    path: list[str]  # Component path from source to target
    total_latency_ms: float
    breakdown: list[tuple[str, str, float]]  # (source, target, latency)
    bottleneck_link: tuple[str, str] | None
    meets_sla: bool
    sla_target_ms: float


# Default latency values when components lack explicit network profiles
_DEFAULT_LOCAL_LATENCY_MS = 5.0
_DEFAULT_CROSS_REGION_LATENCY_MS = 50.0

# Condition multipliers and thresholds
_DEGRADED_LATENCY_MULTIPLIER = 3.0
_DEGRADED_PACKET_LOSS = 0.01

_CONGESTED_LATENCY_MULTIPLIER = 10.0
_CONGESTED_PACKET_LOSS = 0.05

_DNS_FAILURE_PENALTY_MS = 5000.0
_TLS_FAILURE_PENALTY_MS = 3000.0

# Partition sentinel value (unreachable)
_PARTITION_LATENCY_MS = float("inf")


class NetworkSimulator:
    """Simulates network conditions and predicts latency impact.

    Uses the NetworkProfile fields on each Component (jitter_ms,
    packet_loss_rate, dns_resolution_ms, tls_handshake_ms) to model
    realistic network-level failures and their cascading effects.
    """

    def __init__(self, graph: InfraGraph) -> None:
        self.graph = graph

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def simulate(
        self, condition: NetworkCondition | None = None,
    ) -> NetworkSimulationResult:
        """Run a full network simulation under the given condition.

        Parameters
        ----------
        condition:
            The network condition to apply globally.  ``None`` means use
            the current (normal) state of each link.
        """
        links = self._build_links()

        if condition is not None:
            links = [self._apply_condition(link, condition) for link in links]

        healthy = sum(1 for lnk in links if lnk.is_healthy)
        degraded = sum(
            1 for lnk in links
            if not lnk.is_healthy and lnk.condition != NetworkCondition.PARTITIONED
        )
        failed = sum(
            1 for lnk in links
            if not lnk.is_healthy and lnk.condition == NetworkCondition.PARTITIONED
        )

        latencies = [lnk.current_latency_ms for lnk in links if math.isfinite(lnk.current_latency_ms)]
        p50, p95, p99 = self._calculate_percentiles(latencies)

        partition_groups = self._detect_partitions(links)
        partition_detected = len(partition_groups) > 1

        overall_health = self._assess_overall_health(
            healthy, degraded, failed, len(links), partition_detected,
        )

        recommendations = self._generate_recommendations(
            links, partition_detected, partition_groups, p99,
        )

        return NetworkSimulationResult(
            links=links,
            total_links=len(links),
            healthy_links=healthy,
            degraded_links=degraded,
            failed_links=failed,
            p50_latency_ms=p50,
            p95_latency_ms=p95,
            p99_latency_ms=p99,
            partition_detected=partition_detected,
            partition_groups=partition_groups,
            overall_health=overall_health,
            recommendations=recommendations,
        )

    def predict_latency(
        self,
        source_id: str,
        target_id: str,
        sla_ms: float = 500.0,
    ) -> LatencyPrediction:
        """Predict the end-to-end latency between two components.

        Uses the shortest path and sums link latencies along the way.
        """
        path = self._find_shortest_path(source_id, target_id)
        if not path or len(path) < 2:
            return LatencyPrediction(
                path=path,
                total_latency_ms=0.0,
                breakdown=[],
                bottleneck_link=None,
                meets_sla=True,
                sla_target_ms=sla_ms,
            )

        links = self._build_links()
        link_map: dict[tuple[str, str], NetworkLink] = {
            (lnk.source_id, lnk.target_id): lnk for lnk in links
        }

        breakdown: list[tuple[str, str, float]] = []
        total = 0.0
        bottleneck: tuple[str, str] | None = None
        bottleneck_latency = -1.0

        for i in range(len(path) - 1):
            src, tgt = path[i], path[i + 1]
            lnk = link_map.get((src, tgt))
            latency = lnk.current_latency_ms if lnk else self._default_latency(src, tgt)
            breakdown.append((src, tgt, latency))
            total += latency
            if latency > bottleneck_latency:
                bottleneck_latency = latency
                bottleneck = (src, tgt)

        return LatencyPrediction(
            path=path,
            total_latency_ms=total,
            breakdown=breakdown,
            bottleneck_link=bottleneck,
            meets_sla=total <= sla_ms,
            sla_target_ms=sla_ms,
        )

    def simulate_partition(
        self,
        group_a: list[str],
        group_b: list[str],
    ) -> NetworkSimulationResult:
        """Simulate a network partition between two groups of components.

        Links crossing the partition boundary are marked as failed with
        infinite latency.  Links within each group remain normal.
        """
        links = self._build_links()
        set_a = set(group_a)
        set_b = set(group_b)

        partitioned_links: list[NetworkLink] = []
        for lnk in links:
            crosses = (
                (lnk.source_id in set_a and lnk.target_id in set_b)
                or (lnk.source_id in set_b and lnk.target_id in set_a)
            )
            if crosses:
                partitioned_links.append(
                    NetworkLink(
                        source_id=lnk.source_id,
                        target_id=lnk.target_id,
                        base_latency_ms=lnk.base_latency_ms,
                        current_latency_ms=_PARTITION_LATENCY_MS,
                        packet_loss_rate=1.0,
                        condition=NetworkCondition.PARTITIONED,
                        is_healthy=False,
                    )
                )
            else:
                partitioned_links.append(lnk)

        healthy = sum(1 for lnk in partitioned_links if lnk.is_healthy)
        degraded = sum(
            1 for lnk in partitioned_links
            if not lnk.is_healthy and lnk.condition != NetworkCondition.PARTITIONED
        )
        failed = sum(
            1 for lnk in partitioned_links
            if not lnk.is_healthy and lnk.condition == NetworkCondition.PARTITIONED
        )

        latencies = [
            lnk.current_latency_ms
            for lnk in partitioned_links
            if math.isfinite(lnk.current_latency_ms)
        ]
        p50, p95, p99 = self._calculate_percentiles(latencies)

        partition_groups = self._detect_partitions(partitioned_links)
        partition_detected = len(partition_groups) > 1

        overall_health = self._assess_overall_health(
            healthy, degraded, failed, len(partitioned_links), partition_detected,
        )

        recommendations = self._generate_recommendations(
            partitioned_links, partition_detected, partition_groups, p99,
        )

        return NetworkSimulationResult(
            links=partitioned_links,
            total_links=len(partitioned_links),
            healthy_links=healthy,
            degraded_links=degraded,
            failed_links=failed,
            p50_latency_ms=p50,
            p95_latency_ms=p95,
            p99_latency_ms=p99,
            partition_detected=partition_detected,
            partition_groups=partition_groups,
            overall_health=overall_health,
            recommendations=recommendations,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_links(self) -> list[NetworkLink]:
        """Build NetworkLink objects from the graph's dependency edges."""
        links: list[NetworkLink] = []
        for dep in self.graph.all_dependency_edges():
            src_comp = self.graph.get_component(dep.source_id)
            tgt_comp = self.graph.get_component(dep.target_id)

            base_latency = self._compute_base_latency(src_comp, tgt_comp, dep)

            # Start with base latency / loss from component network profiles
            current_latency = base_latency
            packet_loss = 0.0
            if src_comp:
                packet_loss = max(packet_loss, src_comp.network.packet_loss_rate)
            if tgt_comp:
                packet_loss = max(packet_loss, tgt_comp.network.packet_loss_rate)

            # Factor in DNS resolution if either component is DNS type
            if src_comp and src_comp.type == ComponentType.DNS:
                current_latency += src_comp.network.dns_resolution_ms
            if tgt_comp and tgt_comp.type == ComponentType.DNS:
                current_latency += tgt_comp.network.dns_resolution_ms

            # Factor in TLS handshake for components with encryption in transit
            if src_comp and src_comp.security.encryption_in_transit:
                current_latency += src_comp.network.tls_handshake_ms
            if tgt_comp and tgt_comp.security.encryption_in_transit:
                current_latency += tgt_comp.network.tls_handshake_ms

            # Factor in jitter from both ends
            jitter = 0.0
            if src_comp:
                jitter += src_comp.network.jitter_ms
            if tgt_comp:
                jitter += tgt_comp.network.jitter_ms
            current_latency += jitter

            # A link is healthy when both endpoints are healthy and loss < 1%
            is_healthy = True
            if src_comp and src_comp.health in (HealthStatus.DOWN, HealthStatus.OVERLOADED):
                is_healthy = False
            if tgt_comp and tgt_comp.health in (HealthStatus.DOWN, HealthStatus.OVERLOADED):
                is_healthy = False
            if packet_loss >= 0.01:
                is_healthy = False

            links.append(
                NetworkLink(
                    source_id=dep.source_id,
                    target_id=dep.target_id,
                    base_latency_ms=base_latency,
                    current_latency_ms=current_latency,
                    packet_loss_rate=packet_loss,
                    condition=NetworkCondition.NORMAL,
                    is_healthy=is_healthy,
                )
            )
        return links

    def _apply_condition(
        self, link: NetworkLink, condition: NetworkCondition,
    ) -> NetworkLink:
        """Return a *new* NetworkLink with the given condition applied."""
        latency = link.base_latency_ms
        loss = link.packet_loss_rate
        is_healthy = link.is_healthy

        src_comp = self.graph.get_component(link.source_id)
        tgt_comp = self.graph.get_component(link.target_id)

        if condition == NetworkCondition.NORMAL:
            latency = link.current_latency_ms  # keep computed latency
        elif condition == NetworkCondition.DEGRADED:
            latency = link.base_latency_ms * _DEGRADED_LATENCY_MULTIPLIER
            loss = max(loss, _DEGRADED_PACKET_LOSS)
            is_healthy = False
        elif condition == NetworkCondition.CONGESTED:
            latency = link.base_latency_ms * _CONGESTED_LATENCY_MULTIPLIER
            loss = max(loss, _CONGESTED_PACKET_LOSS)
            is_healthy = False
        elif condition == NetworkCondition.PARTITIONED:
            latency = _PARTITION_LATENCY_MS
            loss = 1.0
            is_healthy = False
        elif condition == NetworkCondition.DNS_FAILURE:
            latency = link.base_latency_ms + _DNS_FAILURE_PENALTY_MS
            # Only apply DNS penalty to components that depend on DNS
            if src_comp and src_comp.type == ComponentType.DNS:
                latency += _DNS_FAILURE_PENALTY_MS
            if tgt_comp and tgt_comp.type == ComponentType.DNS:
                latency += _DNS_FAILURE_PENALTY_MS
            is_healthy = False
        elif condition == NetworkCondition.TLS_FAILURE:
            latency = link.base_latency_ms + _TLS_FAILURE_PENALTY_MS
            if src_comp and src_comp.security.encryption_in_transit:
                latency += _TLS_FAILURE_PENALTY_MS
            if tgt_comp and tgt_comp.security.encryption_in_transit:
                latency += _TLS_FAILURE_PENALTY_MS
            is_healthy = False

        return NetworkLink(
            source_id=link.source_id,
            target_id=link.target_id,
            base_latency_ms=link.base_latency_ms,
            current_latency_ms=latency,
            packet_loss_rate=loss,
            condition=condition,
            is_healthy=is_healthy,
        )

    def _find_shortest_path(self, source: str, target: str) -> list[str]:
        """BFS shortest path through the dependency graph."""
        if source == target:
            return [source]

        components = self.graph.components
        if source not in components or target not in components:
            return []

        visited: set[str] = {source}
        queue: deque[list[str]] = deque([[source]])

        while queue:
            path = queue.popleft()
            current = path[-1]
            for dep_comp in self.graph.get_dependencies(current):
                if dep_comp.id == target:
                    return path + [target]
                if dep_comp.id not in visited:
                    visited.add(dep_comp.id)
                    queue.append(path + [dep_comp.id])

        return []

    def _detect_partitions(self, links: list[NetworkLink]) -> list[list[str]]:
        """Detect network partitions via connected-component analysis.

        Only *healthy* (non-infinite-latency) links are considered as
        connectivity edges.  Returns a list of component groups; if all
        components can reach each other, a single group is returned.
        """
        all_ids: set[str] = set(self.graph.components.keys())
        if not all_ids:
            return []

        # Build adjacency from healthy links (bidirectional for connectivity)
        adj: dict[str, set[str]] = {cid: set() for cid in all_ids}
        for lnk in links:
            if lnk.is_healthy or (math.isfinite(lnk.current_latency_ms) and lnk.packet_loss_rate < 1.0):
                if lnk.source_id in adj and lnk.target_id in adj:
                    adj[lnk.source_id].add(lnk.target_id)
                    adj[lnk.target_id].add(lnk.source_id)

        visited: set[str] = set()
        groups: list[list[str]] = []

        for cid in sorted(all_ids):
            if cid in visited:
                continue
            group: list[str] = []
            queue: deque[str] = deque([cid])
            while queue:
                node = queue.popleft()
                if node in visited:
                    continue
                visited.add(node)
                group.append(node)
                for neighbour in sorted(adj[node]):
                    if neighbour not in visited:
                        queue.append(neighbour)
            groups.append(group)

        return groups

    def _calculate_percentiles(
        self, latencies: list[float],
    ) -> tuple[float, float, float]:
        """Return (p50, p95, p99) from a list of latency values."""
        if not latencies:
            return (0.0, 0.0, 0.0)

        sorted_lat = sorted(latencies)
        n = len(sorted_lat)

        def _percentile(pct: float) -> float:
            idx = pct / 100.0 * (n - 1)
            lower = int(math.floor(idx))
            upper = min(lower + 1, n - 1)
            frac = idx - lower
            return sorted_lat[lower] * (1 - frac) + sorted_lat[upper] * frac

        return (_percentile(50), _percentile(95), _percentile(99))

    # ------------------------------------------------------------------
    # Private utilities
    # ------------------------------------------------------------------

    def _compute_base_latency(self, src_comp, tgt_comp, dep) -> float:
        """Determine base latency for a link.

        Priority:
        1. Explicit ``latency_ms`` on the dependency edge.
        2. Average of endpoint RTTs from their NetworkProfile.
        3. Cross-region default if regions differ, else local default.
        """
        if dep.latency_ms > 0:
            return dep.latency_ms

        rtts: list[float] = []
        if src_comp:
            rtts.append(src_comp.network.rtt_ms)
        if tgt_comp:
            rtts.append(tgt_comp.network.rtt_ms)

        if rtts:
            return sum(rtts) / len(rtts)

        # Fallback: cross-region vs local
        if src_comp and tgt_comp:
            if (
                src_comp.region.region
                and tgt_comp.region.region
                and src_comp.region.region != tgt_comp.region.region
            ):
                return _DEFAULT_CROSS_REGION_LATENCY_MS

        return _DEFAULT_LOCAL_LATENCY_MS

    def _default_latency(self, source_id: str, target_id: str) -> float:
        """Fallback latency when no link exists."""
        src = self.graph.get_component(source_id)
        tgt = self.graph.get_component(target_id)
        if src and tgt:
            if (
                src.region.region
                and tgt.region.region
                and src.region.region != tgt.region.region
            ):
                return _DEFAULT_CROSS_REGION_LATENCY_MS
        return _DEFAULT_LOCAL_LATENCY_MS

    @staticmethod
    def _assess_overall_health(
        healthy: int,
        degraded: int,
        failed: int,
        total: int,
        partition_detected: bool,
    ) -> str:
        if total == 0:
            return "healthy"
        if partition_detected or failed > 0:
            return "critical"
        if degraded > 0 or healthy < total:
            return "degraded"
        return "healthy"

    @staticmethod
    def _generate_recommendations(
        links: list[NetworkLink],
        partition_detected: bool,
        partition_groups: list[list[str]],
        p99: float,
    ) -> list[str]:
        recommendations: list[str] = []

        if partition_detected:
            groups_str = " | ".join(
                "[" + ", ".join(g) + "]" for g in partition_groups
            )
            recommendations.append(
                f"Network partition detected. Isolated groups: {groups_str}. "
                "Consider adding redundant network paths."
            )

        high_loss = [
            lnk for lnk in links if lnk.packet_loss_rate >= 0.01
        ]
        if high_loss:
            ids = sorted({lnk.source_id for lnk in high_loss} | {lnk.target_id for lnk in high_loss})
            recommendations.append(
                f"High packet loss (>=1%) detected on links involving: {', '.join(ids)}. "
                "Investigate network quality or add retries."
            )

        if p99 > 500.0:
            recommendations.append(
                f"P99 latency ({p99:.1f}ms) exceeds 500ms. "
                "Consider caching, CDN, or moving services closer together."
            )

        high_latency = [
            lnk for lnk in links
            if math.isfinite(lnk.current_latency_ms) and lnk.current_latency_ms > 100.0
        ]
        if high_latency:
            for lnk in high_latency:
                recommendations.append(
                    f"Link {lnk.source_id} -> {lnk.target_id} has high latency "
                    f"({lnk.current_latency_ms:.1f}ms). Consider optimizing this path."
                )

        return recommendations
