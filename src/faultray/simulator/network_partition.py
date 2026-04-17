# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""Advanced Network Partition Simulator.

Simulates complex network partition scenarios and their impact on
distributed systems, including split-brain detection, CAP theorem
analysis, consensus impact, and healing simulations.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

from faultray.model.components import Component, ComponentType, Dependency
from faultray.model.graph import InfraGraph


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class PartitionType(str, Enum):
    """Types of network partition scenarios."""

    FULL_PARTITION = "full_partition"
    ASYMMETRIC_PARTITION = "asymmetric_partition"
    PARTIAL_PARTITION = "partial_partition"
    FLAPPING = "flapping"
    DNS_PARTITION = "dns_partition"
    SLOW_NETWORK = "slow_network"
    PACKET_REORDER = "packet_reorder"
    MTU_BLACKHOLE = "mtu_blackhole"
    SPLIT_BRAIN = "split_brain"
    BYZANTINE_PARTITION = "byzantine_partition"


class ConsistencyModel(str, Enum):
    """Consistency models for distributed data stores."""

    STRONG = "strong"
    EVENTUAL = "eventual"
    CAUSAL = "causal"
    LINEARIZABLE = "linearizable"
    SEQUENTIAL = "sequential"
    READ_YOUR_WRITES = "read_your_writes"


class PartitionScope(str, Enum):
    """Scope/blast-radius of a partition event."""

    RACK_LEVEL = "rack_level"
    ZONE_LEVEL = "zone_level"
    REGION_LEVEL = "region_level"
    CROSS_REGION = "cross_region"
    SERVICE_MESH = "service_mesh"
    CUSTOM = "custom"


# ---------------------------------------------------------------------------
# Risk tables (exported for test-coverage)
# ---------------------------------------------------------------------------

_PARTITION_SEVERITY: dict[PartitionType, float] = {
    PartitionType.FULL_PARTITION: 1.0,
    PartitionType.ASYMMETRIC_PARTITION: 0.8,
    PartitionType.PARTIAL_PARTITION: 0.5,
    PartitionType.FLAPPING: 0.7,
    PartitionType.DNS_PARTITION: 0.6,
    PartitionType.SLOW_NETWORK: 0.3,
    PartitionType.PACKET_REORDER: 0.4,
    PartitionType.MTU_BLACKHOLE: 0.5,
    PartitionType.SPLIT_BRAIN: 0.95,
    PartitionType.BYZANTINE_PARTITION: 0.9,
}

_SCOPE_MULTIPLIER: dict[PartitionScope, float] = {
    PartitionScope.RACK_LEVEL: 0.3,
    PartitionScope.ZONE_LEVEL: 0.5,
    PartitionScope.REGION_LEVEL: 0.8,
    PartitionScope.CROSS_REGION: 1.0,
    PartitionScope.SERVICE_MESH: 0.6,
    PartitionScope.CUSTOM: 0.5,
}

_CONSISTENCY_RISK: dict[ConsistencyModel, float] = {
    ConsistencyModel.STRONG: 0.2,
    ConsistencyModel.EVENTUAL: 0.8,
    ConsistencyModel.CAUSAL: 0.5,
    ConsistencyModel.LINEARIZABLE: 0.15,
    ConsistencyModel.SEQUENTIAL: 0.3,
    ConsistencyModel.READ_YOUR_WRITES: 0.6,
}

_RECOVERY_BASE_SECONDS: dict[PartitionType, float] = {
    PartitionType.FULL_PARTITION: 120.0,
    PartitionType.ASYMMETRIC_PARTITION: 90.0,
    PartitionType.PARTIAL_PARTITION: 60.0,
    PartitionType.FLAPPING: 180.0,
    PartitionType.DNS_PARTITION: 300.0,
    PartitionType.SLOW_NETWORK: 30.0,
    PartitionType.PACKET_REORDER: 45.0,
    PartitionType.MTU_BLACKHOLE: 90.0,
    PartitionType.SPLIT_BRAIN: 600.0,
    PartitionType.BYZANTINE_PARTITION: 900.0,
}


# ---------------------------------------------------------------------------
# Pydantic Models
# ---------------------------------------------------------------------------


class NetworkPartitionConfig(BaseModel):
    """Configuration for a network partition simulation."""

    partition_type: PartitionType
    scope: PartitionScope
    affected_components: list[str]
    duration_seconds: float = 60.0
    packet_loss_percent: float = 0.0
    added_latency_ms: float = 0.0
    consistency_model: ConsistencyModel = ConsistencyModel.EVENTUAL


class PartitionImpact(BaseModel):
    """Result of a full partition simulation."""

    partition_sides: list[list[str]] = Field(default_factory=list)
    severed_connections: list[tuple[str, str]] = Field(default_factory=list)
    data_inconsistency_risk: str = "low"
    split_brain_possible: bool = False
    estimated_data_loss_events: int = 0
    availability_during_partition: float = 100.0
    recovery_time_seconds: float = 0.0
    recommendations: list[str] = Field(default_factory=list)


class SplitBrainAnalysis(BaseModel):
    """Assessment of split-brain risk."""

    conflicting_writes: int = 0
    resolution_strategy: str = "last_writer_wins"
    data_reconciliation_time_seconds: float = 0.0
    affected_users_estimate: int = 0


class VulnerablePath(BaseModel):
    """A path in the graph that is vulnerable to partitions."""

    path: list[str] = Field(default_factory=list)
    vulnerability_score: float = 0.0
    bottleneck_component: str = ""
    reason: str = ""


class CAPTradeoffResult(BaseModel):
    """CAP theorem analysis for a given partition scenario."""

    consistency_available: bool = True
    availability_available: bool = True
    partition_tolerance: bool = True
    chosen_tradeoff: str = "AP"
    impact_description: str = ""
    consistency_cost: float = 0.0
    availability_cost: float = 0.0


class PartitionRecommendation(BaseModel):
    """Recommendation for improving partition tolerance."""

    component_id: str = ""
    recommendation: str = ""
    priority: str = "medium"
    estimated_effort: str = "medium"


class HealingSimulation(BaseModel):
    """Result of simulating partition healing."""

    healing_time_seconds: float = 0.0
    data_sync_required: bool = False
    sync_volume_estimate: str = "none"
    conflict_resolution_needed: bool = False
    estimated_conflicts: int = 0
    post_healing_consistency: str = "consistent"
    steps: list[str] = Field(default_factory=list)


class ConsensusImpact(BaseModel):
    """Impact of a partition on consensus protocols."""

    quorum_maintained: bool = True
    nodes_in_majority: int = 0
    nodes_in_minority: int = 0
    leader_election_needed: bool = False
    election_time_seconds: float = 0.0
    write_availability: float = 100.0
    read_availability: float = 100.0
    impact_summary: str = ""


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


def _clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    """Clamp *value* between *lo* and *hi*."""
    return max(lo, min(hi, value))


class NetworkPartitionEngine:
    """Stateless engine for network partition simulation and analysis."""

    # ------------------------------------------------------------------
    # simulate_partition
    # ------------------------------------------------------------------

    def simulate_partition(
        self,
        graph: InfraGraph,
        config: NetworkPartitionConfig,
    ) -> PartitionImpact:
        """Run a full partition simulation and return the impact."""
        sides = self._compute_partition_sides(graph, config)
        severed = self._find_severed_connections(graph, config, sides)
        severity = _PARTITION_SEVERITY[config.partition_type]
        scope_mult = _SCOPE_MULTIPLIER[config.scope]
        consistency_risk = _CONSISTENCY_RISK[config.consistency_model]

        risk_score = severity * scope_mult * consistency_risk
        if risk_score >= 0.4:
            risk_label = "high"
        elif risk_score >= 0.15:
            risk_label = "medium"
        else:
            risk_label = "low"

        split_brain = self._is_split_brain_possible(config, sides)

        data_loss_events = self._estimate_data_loss_events(
            config, severed, consistency_risk,
        )

        availability = self._estimate_availability(
            graph, config, sides, severed,
        )

        recovery = self._estimate_recovery_time(config)

        recommendations = self._build_recommendations(
            config, sides, severed, split_brain, risk_label,
        )

        return PartitionImpact(
            partition_sides=sides,
            severed_connections=severed,
            data_inconsistency_risk=risk_label,
            split_brain_possible=split_brain,
            estimated_data_loss_events=data_loss_events,
            availability_during_partition=round(availability, 2),
            recovery_time_seconds=recovery,
            recommendations=recommendations,
        )

    # ------------------------------------------------------------------
    # detect_split_brain_risk
    # ------------------------------------------------------------------

    def detect_split_brain_risk(
        self,
        graph: InfraGraph,
        config: NetworkPartitionConfig,
    ) -> SplitBrainAnalysis:
        """Assess the risk of split-brain for the given partition config."""
        sides = self._compute_partition_sides(graph, config)

        # Count writable components on each side
        writable_types = {
            ComponentType.DATABASE,
            ComponentType.CACHE,
            ComponentType.STORAGE,
            ComponentType.QUEUE,
        }
        writes_per_side: list[int] = []
        for side in sides:
            count = 0
            for cid in side:
                comp = graph.get_component(cid)
                if comp and comp.type in writable_types:
                    count += 1
            writes_per_side.append(count)

        multi_writer = sum(1 for w in writes_per_side if w > 0) > 1
        severity = _PARTITION_SEVERITY[config.partition_type]

        if multi_writer:
            conflicting = max(
                1,
                int(config.duration_seconds / 10 * severity),
            )
        else:
            conflicting = 0

        strategy = self._select_resolution_strategy(config.consistency_model)

        reconciliation = 0.0
        if conflicting > 0:
            reconciliation = conflicting * 2.0 + _RECOVERY_BASE_SECONDS.get(
                config.partition_type, 120.0,
            ) * 0.5

        # Rough user estimate based on duration and severity
        affected_users = int(config.duration_seconds * severity * 10)

        return SplitBrainAnalysis(
            conflicting_writes=conflicting,
            resolution_strategy=strategy,
            data_reconciliation_time_seconds=round(reconciliation, 2),
            affected_users_estimate=affected_users,
        )

    # ------------------------------------------------------------------
    # find_partition_vulnerable_paths
    # ------------------------------------------------------------------

    def find_partition_vulnerable_paths(
        self,
        graph: InfraGraph,
    ) -> list[VulnerablePath]:
        """Identify dependency paths most vulnerable to partitions."""
        paths: list[VulnerablePath] = []
        components = list(graph.components.values())
        if len(components) < 2:
            return paths

        edges = graph.all_dependency_edges()
        if not edges:
            return paths

        for edge in edges:
            src = graph.get_component(edge.source_id)
            tgt = graph.get_component(edge.target_id)
            if not src or not tgt:
                continue

            score = self._path_vulnerability_score(src, tgt, edge)
            if score <= 0:
                continue

            bottleneck = src.id if src.replicas <= tgt.replicas else tgt.id
            reason = self._path_vulnerability_reason(src, tgt, edge)

            paths.append(
                VulnerablePath(
                    path=[src.id, tgt.id],
                    vulnerability_score=round(score, 2),
                    bottleneck_component=bottleneck,
                    reason=reason,
                ),
            )

        paths.sort(key=lambda p: p.vulnerability_score, reverse=True)
        return paths

    # ------------------------------------------------------------------
    # simulate_cap_tradeoff
    # ------------------------------------------------------------------

    def simulate_cap_tradeoff(
        self,
        graph: InfraGraph,
        config: NetworkPartitionConfig,
    ) -> CAPTradeoffResult:
        """Analyse CAP theorem trade-offs for the given partition."""
        severity = _PARTITION_SEVERITY[config.partition_type]
        consistency_risk = _CONSISTENCY_RISK[config.consistency_model]

        partition_tolerance = severity >= 0.3

        if config.consistency_model in (
            ConsistencyModel.STRONG,
            ConsistencyModel.LINEARIZABLE,
        ):
            # CP system: consistency kept, availability sacrificed
            consistency_available = True
            availability_available = False
            tradeoff = "CP"
            availability_cost = severity * 100.0
            consistency_cost = 0.0
        elif config.consistency_model in (
            ConsistencyModel.EVENTUAL,
            ConsistencyModel.READ_YOUR_WRITES,
        ):
            # AP system: availability kept, consistency sacrificed
            consistency_available = False
            availability_available = True
            tradeoff = "AP"
            consistency_cost = consistency_risk * 100.0
            availability_cost = 0.0
        else:
            # Hybrid (causal / sequential)
            consistency_available = severity < 0.5
            availability_available = severity < 0.7
            tradeoff = "balanced"
            consistency_cost = consistency_risk * severity * 100.0
            availability_cost = severity * (1 - consistency_risk) * 100.0

        impact_desc = (
            f"{tradeoff} trade-off under {config.partition_type.value} "
            f"partition with {config.consistency_model.value} consistency"
        )

        return CAPTradeoffResult(
            consistency_available=consistency_available,
            availability_available=availability_available,
            partition_tolerance=partition_tolerance,
            chosen_tradeoff=tradeoff,
            impact_description=impact_desc,
            consistency_cost=round(_clamp(consistency_cost), 2),
            availability_cost=round(_clamp(availability_cost), 2),
        )

    # ------------------------------------------------------------------
    # recommend_partition_tolerance
    # ------------------------------------------------------------------

    def recommend_partition_tolerance(
        self,
        graph: InfraGraph,
    ) -> list[PartitionRecommendation]:
        """Generate recommendations to improve partition tolerance."""
        recs: list[PartitionRecommendation] = []

        for comp in graph.components.values():
            if comp.replicas < 2:
                recs.append(
                    PartitionRecommendation(
                        component_id=comp.id,
                        recommendation=(
                            f"Increase replicas for '{comp.id}' "
                            "to tolerate single-node partitions"
                        ),
                        priority="high",
                        estimated_effort="medium",
                    ),
                )

            if not comp.failover.enabled:
                recs.append(
                    PartitionRecommendation(
                        component_id=comp.id,
                        recommendation=(
                            f"Enable failover for '{comp.id}' "
                            "to improve recovery from partitions"
                        ),
                        priority="high",
                        estimated_effort="medium",
                    ),
                )

            if comp.type == ComponentType.DATABASE and comp.replicas < 3:
                recs.append(
                    PartitionRecommendation(
                        component_id=comp.id,
                        recommendation=(
                            f"Database '{comp.id}' should have >= 3 replicas "
                            "for quorum-based consensus"
                        ),
                        priority="critical",
                        estimated_effort="high",
                    ),
                )

        edges = graph.all_dependency_edges()
        for edge in edges:
            if not edge.circuit_breaker.enabled:
                recs.append(
                    PartitionRecommendation(
                        component_id=edge.source_id,
                        recommendation=(
                            f"Enable circuit breaker on {edge.source_id} -> "
                            f"{edge.target_id} to limit partition blast radius"
                        ),
                        priority="medium",
                        estimated_effort="low",
                    ),
                )

            if not edge.retry_strategy.enabled:
                recs.append(
                    PartitionRecommendation(
                        component_id=edge.source_id,
                        recommendation=(
                            f"Enable retry strategy on {edge.source_id} -> "
                            f"{edge.target_id} for transient partition recovery"
                        ),
                        priority="medium",
                        estimated_effort="low",
                    ),
                )

        return recs

    # ------------------------------------------------------------------
    # simulate_healing
    # ------------------------------------------------------------------

    def simulate_healing(
        self,
        graph: InfraGraph,
        config: NetworkPartitionConfig,
    ) -> HealingSimulation:
        """Simulate what happens when the partition heals."""
        severity = _PARTITION_SEVERITY[config.partition_type]
        consistency_risk = _CONSISTENCY_RISK[config.consistency_model]

        base_healing = _RECOVERY_BASE_SECONDS.get(
            config.partition_type, 120.0,
        )
        healing_time = base_healing * (1 + severity * 0.5)

        data_sync_required = severity >= 0.5 or consistency_risk >= 0.5

        if data_sync_required:
            if config.duration_seconds > 300:
                sync_volume = "large"
            elif config.duration_seconds > 60:
                sync_volume = "medium"
            else:
                sync_volume = "small"
        else:
            sync_volume = "none"

        conflict_needed = (
            config.partition_type
            in (
                PartitionType.SPLIT_BRAIN,
                PartitionType.BYZANTINE_PARTITION,
                PartitionType.FULL_PARTITION,
            )
            and consistency_risk >= 0.5
        )

        estimated_conflicts = 0
        if conflict_needed:
            estimated_conflicts = max(
                1,
                int(config.duration_seconds / 15 * consistency_risk),
            )

        post_consistency = "consistent"
        if conflict_needed and estimated_conflicts > 10:
            post_consistency = "requires_manual_review"
        elif conflict_needed:
            post_consistency = "auto_resolved"
        elif data_sync_required:
            post_consistency = "eventually_consistent"

        steps = self._build_healing_steps(
            config, data_sync_required, conflict_needed,
        )

        return HealingSimulation(
            healing_time_seconds=round(healing_time, 2),
            data_sync_required=data_sync_required,
            sync_volume_estimate=sync_volume,
            conflict_resolution_needed=conflict_needed,
            estimated_conflicts=estimated_conflicts,
            post_healing_consistency=post_consistency,
            steps=steps,
        )

    # ------------------------------------------------------------------
    # analyze_consensus_impact
    # ------------------------------------------------------------------

    def analyze_consensus_impact(
        self,
        graph: InfraGraph,
        config: NetworkPartitionConfig,
    ) -> ConsensusImpact:
        """Analyse impact on consensus protocols (Raft/Paxos-style)."""
        sides = self._compute_partition_sides(graph, config)
        total_nodes = sum(len(s) for s in sides)

        if total_nodes == 0:
            return ConsensusImpact(
                quorum_maintained=False,
                impact_summary="No nodes in partition scope",
            )

        quorum_threshold = total_nodes // 2 + 1

        majority_side = max(sides, key=len) if sides else []
        minority_sides = [s for s in sides if s is not majority_side]
        minority_count = sum(len(s) for s in minority_sides)

        quorum_maintained = len(majority_side) >= quorum_threshold

        leader_election = (
            config.partition_type
            in (
                PartitionType.FULL_PARTITION,
                PartitionType.SPLIT_BRAIN,
                PartitionType.BYZANTINE_PARTITION,
                PartitionType.ASYMMETRIC_PARTITION,
            )
        )

        severity = _PARTITION_SEVERITY[config.partition_type]

        if leader_election:
            election_time = 5.0 + severity * 25.0
        else:
            election_time = 0.0

        if quorum_maintained:
            write_avail = _clamp(
                100.0 - minority_count / max(total_nodes, 1) * 100.0 * severity,
            )
            read_avail = _clamp(
                100.0 - minority_count / max(total_nodes, 1) * 50.0 * severity,
            )
        else:
            write_avail = 0.0
            read_avail = _clamp(
                100.0 - severity * 80.0,
            )

        summary_parts = []
        if quorum_maintained:
            summary_parts.append("Quorum maintained")
        else:
            summary_parts.append("Quorum lost")
        summary_parts.append(
            f"majority={len(majority_side)}, minority={minority_count}"
        )
        if leader_election:
            summary_parts.append(
                f"leader election ~{election_time:.0f}s"
            )

        return ConsensusImpact(
            quorum_maintained=quorum_maintained,
            nodes_in_majority=len(majority_side),
            nodes_in_minority=minority_count,
            leader_election_needed=leader_election,
            election_time_seconds=round(election_time, 2),
            write_availability=round(write_avail, 2),
            read_availability=round(read_avail, 2),
            impact_summary="; ".join(summary_parts),
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_partition_sides(
        graph: InfraGraph,
        config: NetworkPartitionConfig,
    ) -> list[list[str]]:
        """Split components into partition sides."""
        affected = set(config.affected_components)
        all_ids = set(graph.components.keys())

        side_a = sorted(cid for cid in affected if cid in all_ids)
        side_b = sorted(cid for cid in all_ids if cid not in affected)

        sides: list[list[str]] = []
        if side_a:
            sides.append(side_a)
        if side_b:
            sides.append(side_b)
        return sides

    @staticmethod
    def _find_severed_connections(
        graph: InfraGraph,
        config: NetworkPartitionConfig,
        sides: list[list[str]],
    ) -> list[tuple[str, str]]:
        """Identify dependency edges that cross the partition boundary."""
        if len(sides) < 2:
            return []

        side_sets = [set(s) for s in sides]
        severed: list[tuple[str, str]] = []
        edges = graph.all_dependency_edges()
        for edge in edges:
            for i, si in enumerate(side_sets):
                for j, sj in enumerate(side_sets):
                    if i >= j:
                        continue
                    if (edge.source_id in si and edge.target_id in sj) or (
                        edge.source_id in sj and edge.target_id in si
                    ):
                        pair = (edge.source_id, edge.target_id)
                        if pair not in severed:
                            severed.append(pair)
        return severed

    @staticmethod
    def _is_split_brain_possible(
        config: NetworkPartitionConfig,
        sides: list[list[str]],
    ) -> bool:
        """True when split-brain can occur."""
        if len(sides) < 2:
            return False
        if config.partition_type in (
            PartitionType.SPLIT_BRAIN,
            PartitionType.FULL_PARTITION,
            PartitionType.BYZANTINE_PARTITION,
        ):
            return True
        if config.partition_type == PartitionType.ASYMMETRIC_PARTITION:
            return len(sides) >= 2 and all(len(s) > 0 for s in sides)
        return False

    @staticmethod
    def _estimate_data_loss_events(
        config: NetworkPartitionConfig,
        severed: list[tuple[str, str]],
        consistency_risk: float,
    ) -> int:
        """Rough estimate of data-loss events during the partition."""
        if not severed:
            return 0
        base = len(severed) * consistency_risk
        time_factor = config.duration_seconds / 60.0
        severity = _PARTITION_SEVERITY[config.partition_type]
        loss_pct = config.packet_loss_percent / 100.0
        return max(0, int(base * time_factor * severity * (1 + loss_pct)))

    @staticmethod
    def _estimate_availability(
        graph: InfraGraph,
        config: NetworkPartitionConfig,
        sides: list[list[str]],
        severed: list[tuple[str, str]],
    ) -> float:
        """Estimate remaining availability (%) during the partition."""
        total = len(graph.components)
        if total == 0:
            return 100.0

        affected_count = len(config.affected_components)
        severity = _PARTITION_SEVERITY[config.partition_type]
        scope_mult = _SCOPE_MULTIPLIER[config.scope]

        impact_ratio = affected_count / max(total, 1)
        availability = 100.0 * (1 - impact_ratio * severity * scope_mult)

        # Additional penalty for severed connections
        if severed:
            edges_total = len(graph.all_dependency_edges())
            if edges_total > 0:
                severed_ratio = len(severed) / edges_total
                availability -= severed_ratio * 20.0 * severity

        return _clamp(availability)

    @staticmethod
    def _estimate_recovery_time(config: NetworkPartitionConfig) -> float:
        """Estimate time to recover from partition."""
        base = _RECOVERY_BASE_SECONDS[config.partition_type]
        scope_mult = _SCOPE_MULTIPLIER[config.scope]
        # Longer partitions take longer to heal
        duration_factor = 1.0 + config.duration_seconds / 600.0
        return round(base * scope_mult * duration_factor, 2)

    @staticmethod
    def _build_recommendations(
        config: NetworkPartitionConfig,
        sides: list[list[str]],
        severed: list[tuple[str, str]],
        split_brain: bool,
        risk_label: str,
    ) -> list[str]:
        recs: list[str] = []

        if split_brain:
            recs.append(
                "Split-brain risk detected. Implement fencing or "
                "quorum-based leader election."
            )

        if risk_label == "high":
            recs.append(
                "High data inconsistency risk. Consider stronger "
                "consistency guarantees or synchronous replication."
            )

        if len(severed) > 0:
            recs.append(
                f"{len(severed)} connections severed. Add redundant "
                "network paths across partition boundary."
            )

        if config.partition_type == PartitionType.DNS_PARTITION:
            recs.append(
                "DNS partition detected. Deploy local DNS caches "
                "or use IP-based failover."
            )

        if config.partition_type == PartitionType.FLAPPING:
            recs.append(
                "Flapping partition detected. Implement connection "
                "damping and exponential backoff."
            )

        if config.scope in (PartitionScope.CROSS_REGION, PartitionScope.REGION_LEVEL):
            recs.append(
                "Regional partition scope. Ensure multi-region "
                "failover is configured and tested."
            )

        if not recs:
            recs.append("No immediate action required for this partition scenario.")

        return recs

    @staticmethod
    def _select_resolution_strategy(model: ConsistencyModel) -> str:
        """Choose a conflict resolution strategy from the consistency model."""
        strategies: dict[ConsistencyModel, str] = {
            ConsistencyModel.STRONG: "rollback_to_primary",
            ConsistencyModel.EVENTUAL: "last_writer_wins",
            ConsistencyModel.CAUSAL: "causal_merge",
            ConsistencyModel.LINEARIZABLE: "rollback_to_primary",
            ConsistencyModel.SEQUENTIAL: "version_vector",
            ConsistencyModel.READ_YOUR_WRITES: "last_writer_wins",
        }
        return strategies.get(model, "last_writer_wins")

    @staticmethod
    def _path_vulnerability_score(
        src: Component,
        tgt: Component,
        edge: Dependency,
    ) -> float:
        """Compute vulnerability score for a single dependency edge."""
        score = 0.0

        # Single replica penalty
        if src.replicas < 2:
            score += 30.0
        if tgt.replicas < 2:
            score += 30.0

        # No circuit breaker
        if not edge.circuit_breaker.enabled:
            score += 15.0

        # No retry strategy
        if not edge.retry_strategy.enabled:
            score += 10.0

        # Cross-region penalty
        if (
            src.region.region
            and tgt.region.region
            and src.region.region != tgt.region.region
        ):
            score += 20.0

        # Required dependency is riskier
        if edge.dependency_type == "requires":
            score += 10.0
        elif edge.dependency_type == "optional":
            score += 3.0

        # No failover on target
        if not tgt.failover.enabled:
            score += 10.0

        return _clamp(score, 0.0, 100.0)

    @staticmethod
    def _path_vulnerability_reason(
        src: Component,
        tgt: Component,
        edge: Dependency,
    ) -> str:
        """Build a human-readable reason string."""
        reasons: list[str] = []
        if src.replicas < 2:
            reasons.append(f"{src.id} single replica")
        if tgt.replicas < 2:
            reasons.append(f"{tgt.id} single replica")
        if not edge.circuit_breaker.enabled:
            reasons.append("no circuit breaker")
        if edge.dependency_type == "requires":
            reasons.append("hard dependency")
        if not tgt.failover.enabled:
            reasons.append(f"{tgt.id} no failover")
        return "; ".join(reasons) if reasons else "minor risk factors"

    @staticmethod
    def _build_healing_steps(
        config: NetworkPartitionConfig,
        data_sync: bool,
        conflict_resolution: bool,
    ) -> list[str]:
        """Build ordered list of healing steps."""
        steps = ["Detect partition healing"]
        steps.append("Verify network connectivity restored")

        if data_sync:
            steps.append("Initiate data synchronization")

        if conflict_resolution:
            steps.append("Run conflict resolution procedure")

        steps.append("Validate cluster state consistency")

        if config.partition_type in (
            PartitionType.SPLIT_BRAIN,
            PartitionType.BYZANTINE_PARTITION,
        ):
            steps.append("Re-elect cluster leader")

        if config.partition_type == PartitionType.DNS_PARTITION:
            steps.append("Flush DNS caches")

        steps.append("Resume normal operations")
        return steps
