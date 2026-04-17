# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""Data Replication Analyzer.

Analyzes data replication strategies, consistency models, and their resilience
characteristics across distributed infrastructure. Provides replication lag
risk assessment, split-brain detection, conflict resolution analysis,
cross-region latency modeling, replication factor optimization, RPO/data-loss
window calculation, failover sequence analysis, and replica health scoring.

Designed for commercial chaos engineering: helps teams understand how their
replication topology behaves under failure conditions and what tradeoffs
exist between cost, durability, and consistency.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum

from faultray.model.components import HealthStatus
from faultray.model.graph import InfraGraph

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class ReplicationStrategy(str, Enum):
    """Replication strategy for data stores."""

    SYNCHRONOUS = "synchronous"
    ASYNCHRONOUS = "asynchronous"
    SEMI_SYNCHRONOUS = "semi_synchronous"
    QUORUM = "quorum"


class ConsistencyModel(str, Enum):
    """Distributed consistency models."""

    STRONG = "strong"
    EVENTUAL = "eventual"
    CAUSAL = "causal"
    READ_YOUR_WRITES = "read_your_writes"
    MONOTONIC_READS = "monotonic_reads"


class ConflictResolution(str, Enum):
    """Conflict resolution strategies for concurrent writes."""

    LAST_WRITE_WINS = "last_write_wins"
    VECTOR_CLOCKS = "vector_clocks"
    CRDT = "crdt"
    CUSTOM_MERGE = "custom_merge"


class SplitBrainResolution(str, Enum):
    """Strategies for resolving split-brain scenarios."""

    FENCING = "fencing"
    QUORUM_LEADER = "quorum_leader"
    MANUAL = "manual"
    AUTOMATIC_ROLLBACK = "automatic_rollback"


class ReplicaRole(str, Enum):
    """Role of a replica within a replication group."""

    PRIMARY = "primary"
    SECONDARY = "secondary"
    ARBITER = "arbiter"
    WITNESS = "witness"


class RiskLevel(str, Enum):
    """Risk severity level."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class ReplicaNode:
    """A single node participating in a replication group."""

    node_id: str
    component_id: str
    role: ReplicaRole = ReplicaRole.SECONDARY
    region: str = ""
    availability_zone: str = ""
    is_healthy: bool = True
    replication_lag_ms: float = 0.0
    applied_write_sequence: int = 0
    health_score: float = 100.0


@dataclass
class ReplicationGroup:
    """A group of replicas sharing the same data set."""

    group_id: str
    strategy: ReplicationStrategy = ReplicationStrategy.ASYNCHRONOUS
    consistency_model: ConsistencyModel = ConsistencyModel.EVENTUAL
    conflict_resolution: ConflictResolution = ConflictResolution.LAST_WRITE_WINS
    split_brain_resolution: SplitBrainResolution = SplitBrainResolution.MANUAL
    replication_factor: int = 3
    quorum_read: int = 0
    quorum_write: int = 0
    nodes: list[ReplicaNode] = field(default_factory=list)
    cross_region: bool = False


@dataclass
class LagAssessment:
    """Result of analyzing replication lag for a group."""

    group_id: str
    max_lag_ms: float = 0.0
    avg_lag_ms: float = 0.0
    p99_lag_ms: float = 0.0
    lagging_nodes: list[str] = field(default_factory=list)
    risk_level: RiskLevel = RiskLevel.LOW
    estimated_data_loss_window_seconds: float = 0.0
    recommendations: list[str] = field(default_factory=list)


@dataclass
class SplitBrainAssessment:
    """Result of split-brain risk analysis."""

    group_id: str
    is_susceptible: bool = False
    risk_level: RiskLevel = RiskLevel.LOW
    partition_scenarios: list[str] = field(default_factory=list)
    resolution_strategy: SplitBrainResolution = SplitBrainResolution.MANUAL
    estimated_resolution_time_seconds: float = 0.0
    data_divergence_risk: float = 0.0
    recommendations: list[str] = field(default_factory=list)


@dataclass
class FailoverStep:
    """A single step in a failover sequence."""

    step_number: int
    action: str
    target_node_id: str
    estimated_duration_seconds: float = 0.0
    risk_description: str = ""
    data_loss_possible: bool = False


@dataclass
class FailoverPlan:
    """A complete failover sequence for a replication group."""

    group_id: str
    trigger: str = ""
    steps: list[FailoverStep] = field(default_factory=list)
    total_estimated_seconds: float = 0.0
    rpo_seconds: float = 0.0
    rto_seconds: float = 0.0
    risk_level: RiskLevel = RiskLevel.LOW


@dataclass
class ReplicationCostProfile:
    """Cost vs durability tradeoff analysis for a replication factor."""

    replication_factor: int = 1
    storage_cost_multiplier: float = 1.0
    network_cost_multiplier: float = 1.0
    write_latency_multiplier: float = 1.0
    durability_nines: float = 1.0
    annual_data_loss_probability: float = 1.0
    cost_efficiency_score: float = 0.0


@dataclass
class CrossRegionProfile:
    """Cross-region replication latency and risk profile."""

    source_region: str = ""
    target_region: str = ""
    estimated_latency_ms: float = 0.0
    bandwidth_cost_factor: float = 1.0
    consistency_risk: float = 0.0
    regulatory_risk: bool = False


@dataclass
class ReplicationAnalysisReport:
    """Comprehensive replication analysis report."""

    analyzed_at: str = ""
    groups_analyzed: int = 0
    lag_assessments: list[LagAssessment] = field(default_factory=list)
    split_brain_assessments: list[SplitBrainAssessment] = field(default_factory=list)
    failover_plans: list[FailoverPlan] = field(default_factory=list)
    cost_profiles: list[ReplicationCostProfile] = field(default_factory=list)
    cross_region_profiles: list[CrossRegionProfile] = field(default_factory=list)
    overall_replication_health: float = 100.0
    risk_level: RiskLevel = RiskLevel.LOW
    recommendations: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Constants / Lookup Tables
# ---------------------------------------------------------------------------

# Base write latency overhead per strategy (multiplier)
_STRATEGY_WRITE_LATENCY: dict[ReplicationStrategy, float] = {
    ReplicationStrategy.SYNCHRONOUS: 3.0,
    ReplicationStrategy.ASYNCHRONOUS: 1.0,
    ReplicationStrategy.SEMI_SYNCHRONOUS: 2.0,
    ReplicationStrategy.QUORUM: 2.5,
}

# Split-brain susceptibility by strategy
_STRATEGY_SPLIT_BRAIN_SUSCEPTIBILITY: dict[ReplicationStrategy, float] = {
    ReplicationStrategy.SYNCHRONOUS: 0.1,
    ReplicationStrategy.ASYNCHRONOUS: 0.7,
    ReplicationStrategy.SEMI_SYNCHRONOUS: 0.4,
    ReplicationStrategy.QUORUM: 0.2,
}

# Consistency model data loss risk factor (lower = safer)
_CONSISTENCY_DATA_LOSS_FACTOR: dict[ConsistencyModel, float] = {
    ConsistencyModel.STRONG: 0.05,
    ConsistencyModel.EVENTUAL: 0.6,
    ConsistencyModel.CAUSAL: 0.3,
    ConsistencyModel.READ_YOUR_WRITES: 0.35,
    ConsistencyModel.MONOTONIC_READS: 0.4,
}

# Conflict resolution effectiveness (higher = better at preserving data)
_CONFLICT_RESOLUTION_EFFECTIVENESS: dict[ConflictResolution, float] = {
    ConflictResolution.LAST_WRITE_WINS: 0.3,
    ConflictResolution.VECTOR_CLOCKS: 0.8,
    ConflictResolution.CRDT: 0.95,
    ConflictResolution.CUSTOM_MERGE: 0.7,
}

# Split-brain resolution time estimates (seconds)
_SPLIT_BRAIN_RESOLUTION_TIME: dict[SplitBrainResolution, float] = {
    SplitBrainResolution.FENCING: 10.0,
    SplitBrainResolution.QUORUM_LEADER: 30.0,
    SplitBrainResolution.MANUAL: 1800.0,
    SplitBrainResolution.AUTOMATIC_ROLLBACK: 60.0,
}

# Approximate inter-region latency baselines (ms) for common region pairs
_REGION_LATENCY_BASELINES: dict[tuple[str, str], float] = {
    ("us-east-1", "us-west-2"): 62.0,
    ("us-east-1", "eu-west-1"): 85.0,
    ("us-east-1", "ap-northeast-1"): 160.0,
    ("eu-west-1", "ap-northeast-1"): 220.0,
    ("us-west-2", "ap-northeast-1"): 120.0,
    ("us-west-2", "eu-west-1"): 140.0,
}

# Node failure probability per year (individual node)
_NODE_ANNUAL_FAILURE_RATE = 0.04  # 4% annual failure rate


# ---------------------------------------------------------------------------
# Analyzer
# ---------------------------------------------------------------------------


class DataReplicationAnalyzer:
    """Analyzes data replication topologies for resilience characteristics.

    Examines replication groups against the infrastructure graph to determine
    lag risks, split-brain susceptibility, failover readiness, cost tradeoffs,
    and overall replication health.

    Parameters
    ----------
    graph:
        The infrastructure graph containing the components.
    """

    def __init__(self, graph: InfraGraph) -> None:
        self.graph = graph

    # ------------------------------------------------------------------
    # Lag Analysis
    # ------------------------------------------------------------------

    def analyze_replication_lag(self, group: ReplicationGroup) -> LagAssessment:
        """Analyze replication lag characteristics and risk for a group.

        Computes max/avg/p99 lag across nodes, identifies lagging nodes,
        determines the risk level, and estimates the data-loss window.
        """
        if not group.nodes:
            return LagAssessment(
                group_id=group.group_id,
                risk_level=RiskLevel.LOW,
                recommendations=["No nodes in replication group."],
            )

        lags: list[float] = []
        lagging_node_ids: list[str] = []

        for node in group.nodes:
            if node.role == ReplicaRole.ARBITER or node.role == ReplicaRole.WITNESS:
                continue
            lags.append(node.replication_lag_ms)

        if not lags:
            return LagAssessment(
                group_id=group.group_id,
                risk_level=RiskLevel.LOW,
                recommendations=["No data-bearing nodes found."],
            )

        max_lag = max(lags)
        avg_lag = sum(lags) / len(lags)

        # P99 estimation: sort and pick 99th percentile
        sorted_lags = sorted(lags)
        p99_index = max(0, int(math.ceil(len(sorted_lags) * 0.99)) - 1)
        p99_lag = sorted_lags[p99_index]

        # Identify lagging nodes (lag > 2x average, minimum threshold 100ms)
        lag_threshold = max(100.0, avg_lag * 2.0)
        for node in group.nodes:
            if node.role in (ReplicaRole.ARBITER, ReplicaRole.WITNESS):
                continue
            if node.replication_lag_ms > lag_threshold:
                lagging_node_ids.append(node.node_id)

        # Risk level based on max lag and strategy
        risk_level = self._assess_lag_risk(max_lag, group.strategy)

        # Data loss window: for async, max_lag is the window
        data_loss_window = self._calculate_data_loss_window(
            max_lag, group.strategy, group.consistency_model,
        )

        recommendations = self._generate_lag_recommendations(
            max_lag, avg_lag, lagging_node_ids, group,
        )

        return LagAssessment(
            group_id=group.group_id,
            max_lag_ms=max_lag,
            avg_lag_ms=round(avg_lag, 2),
            p99_lag_ms=p99_lag,
            lagging_nodes=lagging_node_ids,
            risk_level=risk_level,
            estimated_data_loss_window_seconds=round(data_loss_window, 3),
            recommendations=recommendations,
        )

    def _assess_lag_risk(
        self, max_lag_ms: float, strategy: ReplicationStrategy,
    ) -> RiskLevel:
        """Determine lag risk level based on max lag and strategy."""
        if strategy == ReplicationStrategy.SYNCHRONOUS:
            # Synchronous should have near-zero lag
            if max_lag_ms > 50:
                return RiskLevel.CRITICAL
            if max_lag_ms > 10:
                return RiskLevel.HIGH
            if max_lag_ms > 1:
                return RiskLevel.MEDIUM
            return RiskLevel.LOW

        if strategy == ReplicationStrategy.SEMI_SYNCHRONOUS:
            if max_lag_ms > 5000:
                return RiskLevel.CRITICAL
            if max_lag_ms > 1000:
                return RiskLevel.HIGH
            if max_lag_ms > 200:
                return RiskLevel.MEDIUM
            return RiskLevel.LOW

        # Async or quorum
        if max_lag_ms > 30000:
            return RiskLevel.CRITICAL
        if max_lag_ms > 10000:
            return RiskLevel.HIGH
        if max_lag_ms > 1000:
            return RiskLevel.MEDIUM
        return RiskLevel.LOW

    def _calculate_data_loss_window(
        self,
        max_lag_ms: float,
        strategy: ReplicationStrategy,
        consistency: ConsistencyModel,
    ) -> float:
        """Calculate the data loss window in seconds (RPO proxy)."""
        if strategy == ReplicationStrategy.SYNCHRONOUS:
            # Zero data loss with synchronous replication (in theory)
            return 0.0

        base_window = max_lag_ms / 1000.0  # Convert ms to seconds

        # Consistency model adjusts the effective window
        consistency_factor = _CONSISTENCY_DATA_LOSS_FACTOR.get(consistency, 0.5)
        # Higher consistency factor = wider real window because more stale
        window = base_window * (1.0 + consistency_factor)

        if strategy == ReplicationStrategy.SEMI_SYNCHRONOUS:
            # At least one replica is up-to-date
            window *= 0.5

        return max(0.0, window)

    def _generate_lag_recommendations(
        self,
        max_lag: float,
        avg_lag: float,
        lagging_nodes: list[str],
        group: ReplicationGroup,
    ) -> list[str]:
        """Generate recommendations for reducing replication lag."""
        recs: list[str] = []

        if max_lag > 10000 and group.strategy == ReplicationStrategy.ASYNCHRONOUS:
            recs.append(
                "Consider semi-synchronous replication to reduce max lag "
                f"(currently {max_lag:.0f}ms)."
            )

        if lagging_nodes:
            recs.append(
                f"Nodes {', '.join(lagging_nodes)} are significantly lagging. "
                "Check network bandwidth and disk I/O on these replicas."
            )

        if group.cross_region and max_lag > 5000:
            recs.append(
                "Cross-region lag is elevated. Consider deploying read replicas "
                "closer to consumers or using a CDN for read-heavy workloads."
            )

        if avg_lag > 1000 and group.strategy == ReplicationStrategy.SYNCHRONOUS:
            recs.append(
                "Synchronous replication with high average lag indicates "
                "write performance issues. Review network latency between nodes."
            )

        if not recs:
            recs.append("Replication lag is within acceptable thresholds.")

        return recs

    # ------------------------------------------------------------------
    # Split-Brain Detection
    # ------------------------------------------------------------------

    def assess_split_brain_risk(
        self, group: ReplicationGroup,
    ) -> SplitBrainAssessment:
        """Evaluate split-brain risk for a replication group.

        Analyzes the replication topology, number of nodes, quorum settings,
        and regional distribution to determine split-brain susceptibility.
        """
        if not group.nodes:
            return SplitBrainAssessment(
                group_id=group.group_id,
                is_susceptible=False,
                risk_level=RiskLevel.LOW,
                recommendations=["No nodes to evaluate."],
            )

        base_susceptibility = _STRATEGY_SPLIT_BRAIN_SUSCEPTIBILITY.get(
            group.strategy, 0.5,
        )

        scenarios: list[str] = []
        risk_factors: float = base_susceptibility

        # Even number of nodes increases split-brain risk
        data_nodes = [
            n for n in group.nodes
            if n.role not in (ReplicaRole.ARBITER, ReplicaRole.WITNESS)
        ]
        has_arbiter = any(
            n.role in (ReplicaRole.ARBITER, ReplicaRole.WITNESS)
            for n in group.nodes
        )

        if len(data_nodes) > 1 and len(data_nodes) % 2 == 0 and not has_arbiter:
            risk_factors += 0.2
            scenarios.append(
                "Even number of data nodes without arbiter; "
                "network partition can create equal-sized partitions."
            )

        # Cross-region deployment increases partition likelihood
        regions = set()
        for node in group.nodes:
            if node.region:
                regions.add(node.region)
        if len(regions) > 1:
            risk_factors += 0.15
            scenarios.append(
                f"Nodes span {len(regions)} regions; inter-region "
                "network partitions are a realistic failure mode."
            )

        # No quorum configuration for quorum strategy is a misconfiguration
        if group.strategy == ReplicationStrategy.QUORUM:
            total_data = len(data_nodes)
            majority = total_data // 2 + 1
            if group.quorum_write < majority:
                risk_factors += 0.25
                scenarios.append(
                    f"Quorum write ({group.quorum_write}) is below majority "
                    f"({majority}); concurrent writes may conflict."
                )
            else:
                risk_factors -= 0.1  # Well-configured quorum

        # Single node is trivially safe from split-brain
        if len(data_nodes) <= 1:
            return SplitBrainAssessment(
                group_id=group.group_id,
                is_susceptible=False,
                risk_level=RiskLevel.LOW,
                data_divergence_risk=0.0,
                resolution_strategy=group.split_brain_resolution,
                estimated_resolution_time_seconds=0.0,
                recommendations=["Single node; split-brain not applicable."],
            )

        # Unhealthy nodes amplify risk
        unhealthy = sum(1 for n in group.nodes if not n.is_healthy)
        if unhealthy > 0:
            risk_factors += 0.1 * min(unhealthy, 3)
            scenarios.append(
                f"{unhealthy} unhealthy node(s) detected; partial failures "
                "can trigger leadership re-election and split-brain."
            )

        risk_factors = min(1.0, max(0.0, risk_factors))

        is_susceptible = risk_factors > 0.3
        risk_level = self._risk_from_score(risk_factors)

        # Data divergence risk combines split-brain risk with conflict resolution
        cr_effectiveness = _CONFLICT_RESOLUTION_EFFECTIVENESS.get(
            group.conflict_resolution, 0.5,
        )
        data_divergence = risk_factors * (1.0 - cr_effectiveness)

        resolution_time = _SPLIT_BRAIN_RESOLUTION_TIME.get(
            group.split_brain_resolution, 600.0,
        )

        recommendations = self._generate_split_brain_recommendations(
            risk_factors, data_nodes, has_arbiter, group,
        )

        return SplitBrainAssessment(
            group_id=group.group_id,
            is_susceptible=is_susceptible,
            risk_level=risk_level,
            partition_scenarios=scenarios,
            resolution_strategy=group.split_brain_resolution,
            estimated_resolution_time_seconds=resolution_time,
            data_divergence_risk=round(data_divergence, 4),
            recommendations=recommendations,
        )

    def _generate_split_brain_recommendations(
        self,
        risk_score: float,
        data_nodes: list[ReplicaNode],
        has_arbiter: bool,
        group: ReplicationGroup,
    ) -> list[str]:
        recs: list[str] = []

        if len(data_nodes) % 2 == 0 and not has_arbiter and len(data_nodes) > 1:
            recs.append(
                "Add an arbiter or witness node to avoid equal-sized partitions."
            )

        if group.split_brain_resolution == SplitBrainResolution.MANUAL:
            recs.append(
                "Manual split-brain resolution has high MTTR. Consider automatic "
                "fencing or quorum-based resolution."
            )

        if group.conflict_resolution == ConflictResolution.LAST_WRITE_WINS:
            recs.append(
                "Last-write-wins conflict resolution can silently discard writes. "
                "Consider vector clocks or CRDTs for better data preservation."
            )

        if risk_score > 0.6:
            recs.append(
                "High split-brain risk. Consider switching to synchronous or "
                "quorum-based replication."
            )

        if not recs:
            recs.append("Split-brain risk is within acceptable bounds.")

        return recs

    # ------------------------------------------------------------------
    # Conflict Resolution Analysis
    # ------------------------------------------------------------------

    def analyze_conflict_resolution(
        self, group: ReplicationGroup,
    ) -> dict:
        """Analyze the effectiveness of the conflict resolution strategy.

        Returns a dictionary with effectiveness score, risks, and
        recommended alternatives.
        """
        effectiveness = _CONFLICT_RESOLUTION_EFFECTIVENESS.get(
            group.conflict_resolution, 0.5,
        )

        risks: list[str] = []
        alternatives: list[str] = []

        if group.conflict_resolution == ConflictResolution.LAST_WRITE_WINS:
            risks.append("Silent data loss when concurrent writes occur.")
            risks.append("Clock skew can cause incorrect winner selection.")
            alternatives.append("vector_clocks")
            alternatives.append("crdt")
        elif group.conflict_resolution == ConflictResolution.VECTOR_CLOCKS:
            risks.append("Storage overhead for maintaining vector timestamps.")
            risks.append("Conflicts still require application-level resolution.")
            alternatives.append("crdt")
        elif group.conflict_resolution == ConflictResolution.CRDT:
            risks.append("Limited to data types with commutative merge operations.")
            risks.append("Increased storage for state-based CRDTs.")
        elif group.conflict_resolution == ConflictResolution.CUSTOM_MERGE:
            risks.append("Custom merge logic must be maintained and tested.")
            risks.append("Bugs in merge logic can cause data corruption.")
            alternatives.append("crdt")

        # Cross-region amplifies conflict risk for weak resolution strategies
        conflict_amplification = 1.0
        if group.cross_region:
            conflict_amplification = 1.5
            if effectiveness < 0.5:
                risks.append(
                    "Cross-region replication with weak conflict resolution "
                    "greatly increases data divergence risk."
                )

        # Consistency model compatibility
        consistency_match = self._consistency_conflict_compatibility(
            group.consistency_model, group.conflict_resolution,
        )

        return {
            "conflict_resolution": group.conflict_resolution.value,
            "effectiveness": round(effectiveness, 2),
            "consistency_compatibility": round(consistency_match, 2),
            "conflict_amplification": round(conflict_amplification, 2),
            "risks": risks,
            "recommended_alternatives": alternatives,
        }

    def _consistency_conflict_compatibility(
        self,
        consistency: ConsistencyModel,
        resolution: ConflictResolution,
    ) -> float:
        """Score how well a consistency model pairs with a conflict strategy.

        Returns 0.0 (poor fit) to 1.0 (excellent fit).
        """
        # Strong consistency + LWW is fine (conflicts are rare)
        if consistency == ConsistencyModel.STRONG:
            return 0.9

        # Eventual consistency needs strong conflict resolution
        if consistency == ConsistencyModel.EVENTUAL:
            if resolution == ConflictResolution.CRDT:
                return 0.95
            if resolution == ConflictResolution.VECTOR_CLOCKS:
                return 0.8
            if resolution == ConflictResolution.CUSTOM_MERGE:
                return 0.6
            return 0.3  # LWW + eventual is risky

        # Causal consistency benefits from vector clocks
        if consistency == ConsistencyModel.CAUSAL:
            if resolution in (ConflictResolution.VECTOR_CLOCKS, ConflictResolution.CRDT):
                return 0.9
            return 0.5

        # Read-your-writes and monotonic are moderate
        base = 0.6
        if resolution in (ConflictResolution.CRDT, ConflictResolution.VECTOR_CLOCKS):
            base = 0.85
        return base

    # ------------------------------------------------------------------
    # Cross-Region Latency Modeling
    # ------------------------------------------------------------------

    def model_cross_region_latency(
        self, group: ReplicationGroup,
    ) -> list[CrossRegionProfile]:
        """Model latency and risk for cross-region replication paths.

        Produces a profile for each pair of regions represented in the group.
        """
        if not group.cross_region:
            return []

        # Collect regions
        region_nodes: dict[str, list[ReplicaNode]] = {}
        for node in group.nodes:
            region = node.region or "unknown"
            region_nodes.setdefault(region, []).append(node)

        regions = list(region_nodes.keys())
        profiles: list[CrossRegionProfile] = []

        for i, src in enumerate(regions):
            for dst in regions[i + 1:]:
                latency = self._estimate_interregion_latency(src, dst)
                bandwidth_cost = 1.0 + (latency / 100.0) * 0.5  # Rough model
                consistency_risk = self._cross_region_consistency_risk(
                    latency, group.strategy, group.consistency_model,
                )

                profiles.append(CrossRegionProfile(
                    source_region=src,
                    target_region=dst,
                    estimated_latency_ms=round(latency, 1),
                    bandwidth_cost_factor=round(bandwidth_cost, 2),
                    consistency_risk=round(consistency_risk, 4),
                    regulatory_risk=src != dst,  # Simplification
                ))

        return profiles

    def _estimate_interregion_latency(self, src: str, dst: str) -> float:
        """Estimate latency between two regions using known baselines."""
        key = (src, dst)
        if key in _REGION_LATENCY_BASELINES:
            return _REGION_LATENCY_BASELINES[key]
        # Try reverse
        reverse_key = (dst, src)
        if reverse_key in _REGION_LATENCY_BASELINES:
            return _REGION_LATENCY_BASELINES[reverse_key]
        # Default: rough estimate based on string heuristics
        if src == dst:
            return 1.0
        return 100.0  # Default cross-region estimate

    def _cross_region_consistency_risk(
        self,
        latency_ms: float,
        strategy: ReplicationStrategy,
        consistency: ConsistencyModel,
    ) -> float:
        """Calculate consistency risk due to cross-region latency."""
        base = latency_ms / 500.0  # Normalize: 500ms latency = risk 1.0

        # Strategy modifiers
        if strategy == ReplicationStrategy.SYNCHRONOUS:
            # Sync tolerates latency but at performance cost
            return min(1.0, base * 0.2)
        if strategy == ReplicationStrategy.SEMI_SYNCHRONOUS:
            return min(1.0, base * 0.5)

        # Async and quorum are more exposed
        consistency_factor = _CONSISTENCY_DATA_LOSS_FACTOR.get(consistency, 0.5)
        return min(1.0, base * (0.7 + consistency_factor * 0.3))

    # ------------------------------------------------------------------
    # Replication Factor Optimization
    # ------------------------------------------------------------------

    def optimize_replication_factor(
        self,
        current_factor: int,
        strategy: ReplicationStrategy,
        target_durability_nines: float = 6.0,
        max_factor: int = 7,
    ) -> list[ReplicationCostProfile]:
        """Analyze cost vs durability tradeoff for different replication factors.

        Returns profiles for factors from 1 up to *max_factor*, each showing
        the storage multiplier, write latency impact, and durability estimate.
        """
        if max_factor < 1:
            max_factor = 1

        profiles: list[ReplicationCostProfile] = []
        write_latency_base = _STRATEGY_WRITE_LATENCY.get(strategy, 1.5)

        for rf in range(1, max_factor + 1):
            storage_mult = float(rf)
            network_mult = max(1.0, float(rf - 1))  # Replication traffic

            # Write latency: synchronous scales with RF, async doesn't
            if strategy == ReplicationStrategy.SYNCHRONOUS:
                wl_mult = write_latency_base * (1.0 + 0.3 * (rf - 1))
            elif strategy == ReplicationStrategy.SEMI_SYNCHRONOUS:
                # Only one extra ack needed
                wl_mult = write_latency_base * (1.0 + 0.1 * min(rf - 1, 1))
            elif strategy == ReplicationStrategy.QUORUM:
                # Quorum size determines latency
                quorum = rf // 2 + 1
                wl_mult = write_latency_base * (1.0 + 0.2 * (quorum - 1))
            else:
                # Async: negligible write latency increase
                wl_mult = write_latency_base

            # Durability: probability of losing all copies
            # P(all fail) = p^rf where p = annual failure rate
            p_all_fail = _NODE_ANNUAL_FAILURE_RATE ** rf
            if p_all_fail > 0:
                durability_nines = -math.log10(p_all_fail)
            else:
                durability_nines = 15.0  # Cap at 15 nines

            annual_loss_prob = p_all_fail

            # Cost efficiency: durability per unit cost
            cost = storage_mult + network_mult * 0.3
            if cost > 0:
                efficiency = durability_nines / cost
            else:
                efficiency = 0.0

            profiles.append(ReplicationCostProfile(
                replication_factor=rf,
                storage_cost_multiplier=round(storage_mult, 2),
                network_cost_multiplier=round(network_mult, 2),
                write_latency_multiplier=round(wl_mult, 2),
                durability_nines=round(durability_nines, 2),
                annual_data_loss_probability=annual_loss_prob,
                cost_efficiency_score=round(efficiency, 4),
            ))

        return profiles

    # ------------------------------------------------------------------
    # RPO / Data Loss Window Calculation
    # ------------------------------------------------------------------

    def calculate_rpo(self, group: ReplicationGroup) -> float:
        """Calculate the Recovery Point Objective in seconds for a group.

        RPO represents the maximum acceptable data loss window. It is
        derived from the replication strategy, consistency model, and
        observed lag.
        """
        if not group.nodes:
            return 0.0

        if group.strategy == ReplicationStrategy.SYNCHRONOUS:
            # Zero RPO for synchronous replication
            return 0.0

        # Find max lag among data-bearing nodes
        max_lag_ms = 0.0
        for node in group.nodes:
            if node.role in (ReplicaRole.ARBITER, ReplicaRole.WITNESS):
                continue
            max_lag_ms = max(max_lag_ms, node.replication_lag_ms)

        base_rpo = max_lag_ms / 1000.0  # Convert to seconds

        # Apply consistency model factor
        consistency_factor = _CONSISTENCY_DATA_LOSS_FACTOR.get(
            group.consistency_model, 0.5,
        )

        # Semi-sync guarantees at least one replica is current
        if group.strategy == ReplicationStrategy.SEMI_SYNCHRONOUS:
            rpo = base_rpo * consistency_factor * 0.5
        elif group.strategy == ReplicationStrategy.QUORUM:
            # Quorum: data is durable once written to majority
            data_nodes = [
                n for n in group.nodes
                if n.role not in (ReplicaRole.ARBITER, ReplicaRole.WITNESS)
            ]
            if len(data_nodes) > 0 and group.quorum_write > 0:
                quorum_coverage = group.quorum_write / len(data_nodes)
                rpo = base_rpo * (1.0 - quorum_coverage) * consistency_factor
            else:
                rpo = base_rpo * consistency_factor
        else:
            # Fully async
            rpo = base_rpo * (1.0 + consistency_factor)

        return round(max(0.0, rpo), 3)

    # ------------------------------------------------------------------
    # Failover Sequence Analysis
    # ------------------------------------------------------------------

    def plan_failover(self, group: ReplicationGroup) -> FailoverPlan:
        """Generate a failover plan for the replication group.

        Identifies the best promotion candidate, generates an ordered
        sequence of failover steps, and estimates RTO/RPO.
        """
        if not group.nodes:
            return FailoverPlan(
                group_id=group.group_id,
                trigger="no_nodes",
                risk_level=RiskLevel.CRITICAL,
            )

        # Find current primary
        primaries = [n for n in group.nodes if n.role == ReplicaRole.PRIMARY]
        secondaries = [
            n for n in group.nodes
            if n.role == ReplicaRole.SECONDARY and n.is_healthy
        ]

        if not primaries:
            return FailoverPlan(
                group_id=group.group_id,
                trigger="no_primary",
                risk_level=RiskLevel.CRITICAL,
                steps=[FailoverStep(
                    step_number=1,
                    action="emergency_election",
                    target_node_id=secondaries[0].node_id if secondaries else "",
                    estimated_duration_seconds=60.0,
                    risk_description="No current primary; emergency election required.",
                    data_loss_possible=True,
                )],
                total_estimated_seconds=60.0,
                rpo_seconds=self.calculate_rpo(group),
                rto_seconds=60.0,
            )

        if not secondaries:
            return FailoverPlan(
                group_id=group.group_id,
                trigger="no_healthy_secondary",
                risk_level=RiskLevel.CRITICAL,
                steps=[FailoverStep(
                    step_number=1,
                    action="await_recovery",
                    target_node_id=primaries[0].node_id,
                    estimated_duration_seconds=300.0,
                    risk_description="No healthy secondaries available for failover.",
                    data_loss_possible=True,
                )],
                total_estimated_seconds=300.0,
                rpo_seconds=self.calculate_rpo(group),
                rto_seconds=300.0,
            )

        # Rank secondaries by promotion priority
        candidates = self._rank_promotion_candidates(secondaries, group)
        best = candidates[0]

        steps: list[FailoverStep] = []
        total_time = 0.0

        # Step 1: Detect primary failure
        detect_time = 10.0
        steps.append(FailoverStep(
            step_number=1,
            action="detect_primary_failure",
            target_node_id=primaries[0].node_id,
            estimated_duration_seconds=detect_time,
            risk_description="Health check detection of primary failure.",
        ))
        total_time += detect_time

        # Step 2: Fence the old primary
        fence_time = 5.0
        steps.append(FailoverStep(
            step_number=2,
            action="fence_old_primary",
            target_node_id=primaries[0].node_id,
            estimated_duration_seconds=fence_time,
            risk_description="STONITH/fencing to prevent split-brain.",
        ))
        total_time += fence_time

        # Step 3: Promote best candidate
        promote_time = self._estimate_promotion_time(best, group)
        data_loss = group.strategy != ReplicationStrategy.SYNCHRONOUS
        steps.append(FailoverStep(
            step_number=3,
            action="promote_secondary",
            target_node_id=best.node_id,
            estimated_duration_seconds=promote_time,
            risk_description=f"Promote {best.node_id} (lag: {best.replication_lag_ms}ms).",
            data_loss_possible=data_loss,
        ))
        total_time += promote_time

        # Step 4: Redirect clients
        redirect_time = 5.0
        steps.append(FailoverStep(
            step_number=4,
            action="redirect_clients",
            target_node_id=best.node_id,
            estimated_duration_seconds=redirect_time,
            risk_description="Update DNS/proxy to point to new primary.",
        ))
        total_time += redirect_time

        # Step 5: Verify replication health
        verify_time = 10.0
        steps.append(FailoverStep(
            step_number=5,
            action="verify_replication_health",
            target_node_id=best.node_id,
            estimated_duration_seconds=verify_time,
            risk_description="Confirm all remaining replicas are replicating.",
        ))
        total_time += verify_time

        rpo = self.calculate_rpo(group)
        risk = self._failover_risk_level(group, best)

        return FailoverPlan(
            group_id=group.group_id,
            trigger="primary_failure",
            steps=steps,
            total_estimated_seconds=round(total_time, 1),
            rpo_seconds=rpo,
            rto_seconds=round(total_time, 1),
            risk_level=risk,
        )

    def _rank_promotion_candidates(
        self,
        candidates: list[ReplicaNode],
        group: ReplicationGroup,
    ) -> list[ReplicaNode]:
        """Rank secondary nodes by promotion priority.

        Priority factors:
        1. Health score (higher is better)
        2. Replication lag (lower is better)
        3. Same region as primary (preferred)
        """
        primaries = [n for n in group.nodes if n.role == ReplicaRole.PRIMARY]
        primary_region = primaries[0].region if primaries else ""

        def score(node: ReplicaNode) -> tuple[float, float, int]:
            health = node.health_score
            lag_penalty = node.replication_lag_ms
            region_bonus = 0 if node.region == primary_region else 1
            return (-health, lag_penalty, region_bonus)

        return sorted(candidates, key=score)

    def _estimate_promotion_time(
        self, candidate: ReplicaNode, group: ReplicationGroup,
    ) -> float:
        """Estimate how long it takes to promote a secondary to primary."""
        base = 15.0  # Base promotion time

        # Lag increases promotion time (replay needed)
        replay_time = candidate.replication_lag_ms / 100.0
        total = base + replay_time

        # Cross-region adds DNS propagation delay
        if group.cross_region:
            total += 10.0

        return round(total, 1)

    def _failover_risk_level(
        self, group: ReplicationGroup, candidate: ReplicaNode,
    ) -> RiskLevel:
        """Determine the overall risk level of a failover operation."""
        if group.strategy == ReplicationStrategy.SYNCHRONOUS and candidate.replication_lag_ms < 10:
            return RiskLevel.LOW
        if candidate.replication_lag_ms > 10000:
            return RiskLevel.CRITICAL
        if candidate.replication_lag_ms > 1000:
            return RiskLevel.HIGH
        if group.strategy == ReplicationStrategy.ASYNCHRONOUS:
            return RiskLevel.MEDIUM
        return RiskLevel.LOW

    # ------------------------------------------------------------------
    # Replica Health Scoring
    # ------------------------------------------------------------------

    def score_replica_health(self, group: ReplicationGroup) -> dict:
        """Score the health of each replica and the group as a whole.

        Returns a dict with per-node scores and an aggregate group score.
        """
        if not group.nodes:
            return {
                "group_id": group.group_id,
                "group_health": 0.0,
                "node_scores": {},
                "degraded_nodes": [],
                "recommendations": ["No nodes in group."],
            }

        node_scores: dict[str, float] = {}
        degraded: list[str] = []

        for node in group.nodes:
            score = self._calculate_node_health(node, group)
            node_scores[node.node_id] = round(score, 1)
            if score < 70.0:
                degraded.append(node.node_id)

        # Group health is weighted average (primaries count double)
        total_weight = 0.0
        weighted_sum = 0.0
        for node in group.nodes:
            weight = 2.0 if node.role == ReplicaRole.PRIMARY else 1.0
            weighted_sum += node_scores[node.node_id] * weight
            total_weight += weight

        group_health = weighted_sum / total_weight if total_weight > 0 else 0.0

        recs: list[str] = []
        if degraded:
            recs.append(
                f"Degraded nodes: {', '.join(degraded)}. "
                "Investigate lag, connectivity, or resource constraints."
            )
        if group_health < 50.0:
            recs.append(
                "Group health is critically low. Immediate investigation required."
            )
        if not recs:
            recs.append("All replicas are healthy.")

        return {
            "group_id": group.group_id,
            "group_health": round(group_health, 1),
            "node_scores": node_scores,
            "degraded_nodes": degraded,
            "recommendations": recs,
        }

    def _calculate_node_health(
        self, node: ReplicaNode, group: ReplicationGroup,
    ) -> float:
        """Calculate health score (0-100) for a single replica node."""
        score = 100.0

        # Unhealthy node
        if not node.is_healthy:
            score -= 50.0

        # Replication lag penalty
        if node.role not in (ReplicaRole.ARBITER, ReplicaRole.WITNESS):
            if node.replication_lag_ms > 10000:
                score -= 30.0
            elif node.replication_lag_ms > 5000:
                score -= 20.0
            elif node.replication_lag_ms > 1000:
                score -= 10.0
            elif node.replication_lag_ms > 100:
                score -= 5.0

        # Check corresponding infrastructure component
        comp = self.graph.get_component(node.component_id)
        if comp is not None:
            # Resource utilization penalty
            util = comp.utilization()
            if util > 90:
                score -= 15.0
            elif util > 80:
                score -= 10.0
            elif util > 70:
                score -= 5.0

            # Health status of the component
            if comp.health == HealthStatus.DOWN:
                score -= 30.0
            elif comp.health == HealthStatus.DEGRADED:
                score -= 15.0
            elif comp.health == HealthStatus.OVERLOADED:
                score -= 20.0

        # Explicit health_score from the node itself
        if node.health_score < 100.0:
            score = min(score, node.health_score)

        return max(0.0, min(100.0, score))

    # ------------------------------------------------------------------
    # Comprehensive Report
    # ------------------------------------------------------------------

    def generate_report(
        self, groups: list[ReplicationGroup],
    ) -> ReplicationAnalysisReport:
        """Generate a full replication analysis report across all groups.

        Runs lag analysis, split-brain assessment, failover planning,
        cost optimization, and cross-region modeling for each group.
        """
        now = datetime.now(timezone.utc).isoformat()

        if not groups:
            return ReplicationAnalysisReport(
                analyzed_at=now,
                groups_analyzed=0,
                overall_replication_health=0.0,
                risk_level=RiskLevel.LOW,
                recommendations=["No replication groups provided for analysis."],
            )

        lag_assessments: list[LagAssessment] = []
        sb_assessments: list[SplitBrainAssessment] = []
        failover_plans: list[FailoverPlan] = []
        cost_profiles: list[ReplicationCostProfile] = []
        cross_region_profiles: list[CrossRegionProfile] = []
        all_recommendations: list[str] = []
        health_scores: list[float] = []

        for group in groups:
            # Lag
            lag = self.analyze_replication_lag(group)
            lag_assessments.append(lag)
            all_recommendations.extend(lag.recommendations)

            # Split-brain
            sb = self.assess_split_brain_risk(group)
            sb_assessments.append(sb)
            all_recommendations.extend(sb.recommendations)

            # Failover
            fo = self.plan_failover(group)
            failover_plans.append(fo)

            # Cost optimization (use current factor)
            costs = self.optimize_replication_factor(
                group.replication_factor, group.strategy,
            )
            cost_profiles.extend(costs)

            # Cross-region
            cr = self.model_cross_region_latency(group)
            cross_region_profiles.extend(cr)

            # Health
            health = self.score_replica_health(group)
            health_scores.append(health["group_health"])
            all_recommendations.extend(health["recommendations"])

        # Aggregate health
        overall_health = (
            sum(health_scores) / len(health_scores) if health_scores else 0.0
        )

        # Determine overall risk
        risk = self._aggregate_risk_level(
            lag_assessments, sb_assessments, failover_plans,
        )

        # Deduplicate recommendations
        seen: set[str] = set()
        unique_recs: list[str] = []
        for r in all_recommendations:
            if r not in seen:
                seen.add(r)
                unique_recs.append(r)

        return ReplicationAnalysisReport(
            analyzed_at=now,
            groups_analyzed=len(groups),
            lag_assessments=lag_assessments,
            split_brain_assessments=sb_assessments,
            failover_plans=failover_plans,
            cost_profiles=cost_profiles,
            cross_region_profiles=cross_region_profiles,
            overall_replication_health=round(overall_health, 1),
            risk_level=risk,
            recommendations=unique_recs,
        )

    def _aggregate_risk_level(
        self,
        lags: list[LagAssessment],
        sbs: list[SplitBrainAssessment],
        fos: list[FailoverPlan],
    ) -> RiskLevel:
        """Determine the worst-case risk level across all assessments."""
        levels = [RiskLevel.LOW]

        for la in lags:
            levels.append(la.risk_level)
        for sb in sbs:
            levels.append(sb.risk_level)
        for fo in fos:
            levels.append(fo.risk_level)

        severity_order = {
            RiskLevel.LOW: 0,
            RiskLevel.MEDIUM: 1,
            RiskLevel.HIGH: 2,
            RiskLevel.CRITICAL: 3,
        }

        return max(levels, key=lambda rl: severity_order.get(rl, 0))

    # ------------------------------------------------------------------
    # Utility Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _risk_from_score(score: float) -> RiskLevel:
        """Convert a 0.0-1.0 risk score into a RiskLevel enum."""
        if score >= 0.7:
            return RiskLevel.CRITICAL
        if score >= 0.5:
            return RiskLevel.HIGH
        if score >= 0.3:
            return RiskLevel.MEDIUM
        return RiskLevel.LOW
