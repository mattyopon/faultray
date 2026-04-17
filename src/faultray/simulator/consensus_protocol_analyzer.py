# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""Consensus Protocol Analyzer.

Analyzes distributed consensus protocols and their resilience characteristics
across infrastructure topologies. Provides Raft/Paxos/ZAB quorum analysis,
split-brain detection and prevention strategies, leader election failure
impact modeling, network partition tolerance (Byzantine fault analysis),
consensus latency modeling under failure scenarios, quorum loss recovery
time estimation, write availability during partial failures, CAP theorem
trade-off scoring, consensus protocol comparison for workloads, voter
membership change impact analysis, log replication lag assessment, and
witness/observer node effectiveness evaluation.

Designed for commercial chaos engineering: helps teams understand how
consensus-dependent systems behave under failure conditions and where
to invest in resilience improvements.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum

from faultray.model.components import Component, ComponentType
from faultray.model.graph import InfraGraph

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class ConsensusProtocol(str, Enum):
    """Supported distributed consensus protocols."""

    RAFT = "raft"
    PAXOS = "paxos"
    ZAB = "zab"
    PBFT = "pbft"
    VIEWSTAMPED = "viewstamped"


class NodeRole(str, Enum):
    """Role of a node in a consensus cluster."""

    LEADER = "leader"
    FOLLOWER = "follower"
    CANDIDATE = "candidate"
    OBSERVER = "observer"
    WITNESS = "witness"
    LEARNER = "learner"


class PartitionType(str, Enum):
    """Types of network partition scenarios."""

    SYMMETRIC = "symmetric"
    ASYMMETRIC = "asymmetric"
    PARTIAL = "partial"
    TOTAL = "total"


class RiskLevel(str, Enum):
    """Risk severity level."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class WorkloadType(str, Enum):
    """Workload profile for protocol comparison."""

    READ_HEAVY = "read_heavy"
    WRITE_HEAVY = "write_heavy"
    BALANCED = "balanced"
    LATENCY_SENSITIVE = "latency_sensitive"
    THROUGHPUT_OPTIMIZED = "throughput_optimized"


class CAPPreference(str, Enum):
    """CAP theorem preference axis."""

    CONSISTENCY = "consistency"
    AVAILABILITY = "availability"
    PARTITION_TOLERANCE = "partition_tolerance"


class MembershipChangeType(str, Enum):
    """Types of voter membership changes."""

    ADD_VOTER = "add_voter"
    REMOVE_VOTER = "remove_voter"
    ADD_OBSERVER = "add_observer"
    REMOVE_OBSERVER = "remove_observer"
    PROMOTE_OBSERVER = "promote_observer"
    DEMOTE_VOTER = "demote_voter"


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class ConsensusNode:
    """A single node participating in a consensus cluster."""

    node_id: str
    component_id: str
    role: NodeRole = NodeRole.FOLLOWER
    region: str = ""
    availability_zone: str = ""
    is_healthy: bool = True
    term: int = 0
    log_index: int = 0
    commit_index: int = 0
    last_heartbeat_ms: float = 0.0
    vote_granted: bool = False
    latency_ms: float = 5.0


@dataclass
class ConsensusCluster:
    """A cluster of nodes running a consensus protocol."""

    cluster_id: str
    protocol: ConsensusProtocol = ConsensusProtocol.RAFT
    nodes: list[ConsensusNode] = field(default_factory=list)
    election_timeout_ms: float = 150.0
    heartbeat_interval_ms: float = 50.0
    max_log_entries_per_batch: int = 100
    snapshot_threshold: int = 10000
    pre_vote_enabled: bool = False
    learner_promotion_threshold: int = 0


@dataclass
class QuorumAnalysis:
    """Result of quorum requirement analysis."""

    cluster_id: str
    total_voters: int = 0
    total_observers: int = 0
    quorum_size: int = 0
    max_tolerable_failures: int = 0
    current_healthy_voters: int = 0
    has_quorum: bool = True
    quorum_margin: int = 0
    risk_level: RiskLevel = RiskLevel.LOW
    recommendations: list[str] = field(default_factory=list)


@dataclass
class SplitBrainAnalysis:
    """Result of split-brain risk analysis."""

    cluster_id: str
    is_susceptible: bool = False
    risk_level: RiskLevel = RiskLevel.LOW
    partition_scenarios: list[str] = field(default_factory=list)
    prevention_mechanisms: list[str] = field(default_factory=list)
    estimated_detection_time_ms: float = 0.0
    estimated_resolution_time_ms: float = 0.0
    dual_leader_probability: float = 0.0
    recommendations: list[str] = field(default_factory=list)


@dataclass
class LeaderElectionImpact:
    """Impact assessment of leader election failure."""

    cluster_id: str
    current_leader_id: str = ""
    election_timeout_ms: float = 0.0
    estimated_downtime_ms: float = 0.0
    write_unavailability_ms: float = 0.0
    read_availability_during_election: bool = False
    candidate_count: int = 0
    risk_of_split_vote: float = 0.0
    pre_vote_reduces_disruption: bool = False
    risk_level: RiskLevel = RiskLevel.LOW
    recommendations: list[str] = field(default_factory=list)


@dataclass
class PartitionToleranceResult:
    """Result of network partition tolerance analysis."""

    cluster_id: str
    partition_type: PartitionType = PartitionType.SYMMETRIC
    surviving_partition_size: int = 0
    isolated_partition_size: int = 0
    maintains_quorum: bool = False
    byzantine_fault_tolerance: int = 0
    max_byzantine_nodes: int = 0
    safety_preserved: bool = True
    liveness_preserved: bool = True
    risk_level: RiskLevel = RiskLevel.LOW
    recommendations: list[str] = field(default_factory=list)


@dataclass
class ConsensusLatencyModel:
    """Latency characteristics under different failure scenarios."""

    cluster_id: str
    normal_commit_latency_ms: float = 0.0
    degraded_commit_latency_ms: float = 0.0
    one_node_failure_latency_ms: float = 0.0
    two_node_failure_latency_ms: float = 0.0
    cross_region_latency_ms: float = 0.0
    leader_in_minority_latency_ms: float = 0.0
    p50_latency_ms: float = 0.0
    p99_latency_ms: float = 0.0
    risk_level: RiskLevel = RiskLevel.LOW
    recommendations: list[str] = field(default_factory=list)


@dataclass
class QuorumRecoveryEstimate:
    """Estimation of recovery time after quorum loss."""

    cluster_id: str
    nodes_to_recover: int = 0
    estimated_recovery_time_ms: float = 0.0
    snapshot_transfer_time_ms: float = 0.0
    log_replay_time_ms: float = 0.0
    leader_election_time_ms: float = 0.0
    total_unavailability_ms: float = 0.0
    data_at_risk: bool = False
    risk_level: RiskLevel = RiskLevel.LOW
    recommendations: list[str] = field(default_factory=list)


@dataclass
class WriteAvailabilityAssessment:
    """Assessment of write availability during partial failures."""

    cluster_id: str
    total_nodes: int = 0
    failed_nodes: int = 0
    writes_available: bool = True
    write_throughput_factor: float = 1.0
    latency_increase_factor: float = 1.0
    durability_factor: float = 1.0
    risk_level: RiskLevel = RiskLevel.LOW
    recommendations: list[str] = field(default_factory=list)


@dataclass
class CAPScore:
    """CAP theorem trade-off scoring."""

    cluster_id: str
    consistency_score: float = 0.0
    availability_score: float = 0.0
    partition_tolerance_score: float = 0.0
    primary_preference: CAPPreference = CAPPreference.CONSISTENCY
    trade_off_description: str = ""
    recommendations: list[str] = field(default_factory=list)


@dataclass
class ProtocolComparison:
    """Comparison of consensus protocols for a given workload."""

    workload: WorkloadType = WorkloadType.BALANCED
    rankings: list[ProtocolRanking] = field(default_factory=list)  # noqa: F821
    best_fit: ConsensusProtocol = ConsensusProtocol.RAFT
    rationale: str = ""
    recommendations: list[str] = field(default_factory=list)


@dataclass
class ProtocolRanking:
    """Ranking entry for a single protocol."""

    protocol: ConsensusProtocol = ConsensusProtocol.RAFT
    latency_score: float = 0.0
    throughput_score: float = 0.0
    fault_tolerance_score: float = 0.0
    complexity_score: float = 0.0
    overall_score: float = 0.0


@dataclass
class MembershipChangeImpact:
    """Impact assessment of a voter membership change."""

    cluster_id: str
    change_type: MembershipChangeType = MembershipChangeType.ADD_VOTER
    node_id: str = ""
    quorum_before: int = 0
    quorum_after: int = 0
    fault_tolerance_before: int = 0
    fault_tolerance_after: int = 0
    requires_joint_consensus: bool = False
    risk_during_transition: RiskLevel = RiskLevel.LOW
    estimated_transition_time_ms: float = 0.0
    recommendations: list[str] = field(default_factory=list)


@dataclass
class LogReplicationLag:
    """Assessment of log replication lag across the cluster."""

    cluster_id: str
    leader_log_index: int = 0
    min_follower_index: int = 0
    max_follower_index: int = 0
    avg_lag_entries: float = 0.0
    max_lag_entries: int = 0
    max_lag_ms: float = 0.0
    lagging_nodes: list[str] = field(default_factory=list)
    risk_level: RiskLevel = RiskLevel.LOW
    recommendations: list[str] = field(default_factory=list)


@dataclass
class WitnessEffectiveness:
    """Evaluation of witness/observer node effectiveness."""

    cluster_id: str
    witness_count: int = 0
    observer_count: int = 0
    quorum_contribution: bool = False
    failover_speed_improvement_ms: float = 0.0
    cost_efficiency_ratio: float = 0.0
    split_brain_prevention: bool = False
    risk_level: RiskLevel = RiskLevel.LOW
    recommendations: list[str] = field(default_factory=list)


@dataclass
class ConsensusAnalysisReport:
    """Comprehensive consensus protocol analysis report."""

    analyzed_at: str = ""
    clusters_analyzed: int = 0
    quorum_analyses: list[QuorumAnalysis] = field(default_factory=list)
    split_brain_analyses: list[SplitBrainAnalysis] = field(default_factory=list)
    leader_election_impacts: list[LeaderElectionImpact] = field(default_factory=list)
    partition_tolerance_results: list[PartitionToleranceResult] = field(
        default_factory=list
    )
    latency_models: list[ConsensusLatencyModel] = field(default_factory=list)
    recovery_estimates: list[QuorumRecoveryEstimate] = field(default_factory=list)
    write_availability: list[WriteAvailabilityAssessment] = field(default_factory=list)
    cap_scores: list[CAPScore] = field(default_factory=list)
    log_replication_lags: list[LogReplicationLag] = field(default_factory=list)
    witness_evaluations: list[WitnessEffectiveness] = field(default_factory=list)
    membership_impacts: list[MembershipChangeImpact] = field(default_factory=list)
    overall_health: float = 100.0
    risk_level: RiskLevel = RiskLevel.LOW
    recommendations: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Constants / Lookup Tables
# ---------------------------------------------------------------------------

# Base commit latency per protocol (ms) for a 3-node cluster
_PROTOCOL_BASE_LATENCY: dict[ConsensusProtocol, float] = {
    ConsensusProtocol.RAFT: 5.0,
    ConsensusProtocol.PAXOS: 8.0,
    ConsensusProtocol.ZAB: 6.0,
    ConsensusProtocol.PBFT: 15.0,
    ConsensusProtocol.VIEWSTAMPED: 7.0,
}

# Protocol complexity scores (1=simple, 10=very complex)
_PROTOCOL_COMPLEXITY: dict[ConsensusProtocol, float] = {
    ConsensusProtocol.RAFT: 3.0,
    ConsensusProtocol.PAXOS: 8.0,
    ConsensusProtocol.ZAB: 5.0,
    ConsensusProtocol.PBFT: 9.0,
    ConsensusProtocol.VIEWSTAMPED: 6.0,
}

# Protocol throughput factor (relative to Raft baseline of 1.0)
_PROTOCOL_THROUGHPUT: dict[ConsensusProtocol, float] = {
    ConsensusProtocol.RAFT: 1.0,
    ConsensusProtocol.PAXOS: 0.85,
    ConsensusProtocol.ZAB: 0.95,
    ConsensusProtocol.PBFT: 0.5,
    ConsensusProtocol.VIEWSTAMPED: 0.9,
}

# Byzantine fault tolerance capability (True = designed for it)
_PROTOCOL_BFT: dict[ConsensusProtocol, bool] = {
    ConsensusProtocol.RAFT: False,
    ConsensusProtocol.PAXOS: False,
    ConsensusProtocol.ZAB: False,
    ConsensusProtocol.PBFT: True,
    ConsensusProtocol.VIEWSTAMPED: False,
}

# Cross-region latency estimates (ms)
_REGION_LATENCY: dict[str, float] = {
    "same_az": 0.5,
    "same_region": 2.0,
    "cross_region": 50.0,
    "cross_continent": 150.0,
}

# Recovery time components (ms per entry)
_LOG_REPLAY_MS_PER_ENTRY = 0.01
_SNAPSHOT_TRANSFER_MS_PER_MB = 100.0
_DEFAULT_SNAPSHOT_SIZE_MB = 50.0


# ---------------------------------------------------------------------------
# Analyzer
# ---------------------------------------------------------------------------


class ConsensusProtocolAnalyzer:
    """Analyzes distributed consensus protocols and their resilience.

    Provides comprehensive analysis of consensus clusters including quorum
    analysis, split-brain detection, leader election impact modeling,
    partition tolerance, latency modeling, and CAP trade-off scoring.
    """

    def __init__(self, graph: InfraGraph) -> None:
        self._graph = graph
        self._clusters: list[ConsensusCluster] = []

    @property
    def clusters(self) -> list[ConsensusCluster]:
        """Return registered clusters."""
        return list(self._clusters)

    # -- Registration -------------------------------------------------------

    def add_cluster(self, cluster: ConsensusCluster) -> None:
        """Register a consensus cluster for analysis."""
        if not cluster.cluster_id:
            raise ValueError("cluster_id must not be empty")
        for existing in self._clusters:
            if existing.cluster_id == cluster.cluster_id:
                raise ValueError(
                    f"Cluster '{cluster.cluster_id}' already registered"
                )
        self._clusters.append(cluster)

    def remove_cluster(self, cluster_id: str) -> bool:
        """Remove a registered cluster. Returns True if found."""
        for i, c in enumerate(self._clusters):
            if c.cluster_id == cluster_id:
                self._clusters.pop(i)
                return True
        return False

    # -- Quorum Analysis ----------------------------------------------------

    def _count_voters(self, cluster: ConsensusCluster) -> tuple[int, int, int]:
        """Return (total_voters, healthy_voters, observer_count)."""
        voters = 0
        healthy = 0
        observers = 0
        for n in cluster.nodes:
            if n.role in (NodeRole.OBSERVER, NodeRole.LEARNER):
                observers += 1
            elif n.role == NodeRole.WITNESS:
                voters += 1
                if n.is_healthy:
                    healthy += 1
            else:
                voters += 1
                if n.is_healthy:
                    healthy += 1
        return voters, healthy, observers

    def analyze_quorum(self, cluster: ConsensusCluster) -> QuorumAnalysis:
        """Analyze quorum requirements and current quorum health."""
        total_voters, healthy_voters, observers = self._count_voters(cluster)

        if cluster.protocol == ConsensusProtocol.PBFT:
            quorum_size = (2 * total_voters // 3) + 1
            max_failures = (total_voters - 1) // 3
        else:
            quorum_size = (total_voters // 2) + 1
            max_failures = total_voters - quorum_size

        has_quorum = healthy_voters >= quorum_size
        margin = healthy_voters - quorum_size

        if margin < 0:
            risk = RiskLevel.CRITICAL
        elif margin == 0:
            risk = RiskLevel.HIGH
        elif margin == 1:
            risk = RiskLevel.MEDIUM
        else:
            risk = RiskLevel.LOW

        recs: list[str] = []
        if not has_quorum:
            recs.append(
                f"Quorum lost: {healthy_voters}/{quorum_size} voters healthy. "
                "Immediate recovery required."
            )
        if margin == 0:
            recs.append(
                "No quorum margin. One more failure causes quorum loss."
            )
        if total_voters < 3:
            recs.append(
                "Cluster has fewer than 3 voters. Increase to at least 3 "
                "for fault tolerance."
            )
        if total_voters % 2 == 0:
            recs.append(
                "Even number of voters provides no benefit over N-1. "
                "Use odd voter counts."
            )
        if observers == 0 and total_voters >= 5:
            recs.append(
                "Consider adding observer nodes for read scaling "
                "without quorum overhead."
            )

        return QuorumAnalysis(
            cluster_id=cluster.cluster_id,
            total_voters=total_voters,
            total_observers=observers,
            quorum_size=quorum_size,
            max_tolerable_failures=max_failures,
            current_healthy_voters=healthy_voters,
            has_quorum=has_quorum,
            quorum_margin=margin,
            risk_level=risk,
            recommendations=recs,
        )

    # -- Split-Brain Detection ----------------------------------------------

    def analyze_split_brain(
        self, cluster: ConsensusCluster
    ) -> SplitBrainAnalysis:
        """Detect split-brain susceptibility and prevention strategies."""
        total_voters, healthy_voters, _ = self._count_voters(cluster)
        scenarios: list[str] = []
        prevention: list[str] = []
        dual_leader_prob = 0.0

        # Determine region distribution
        regions: dict[str, int] = {}
        for n in cluster.nodes:
            if n.role not in (NodeRole.OBSERVER, NodeRole.LEARNER):
                r = n.region or "default"
                regions[r] = regions.get(r, 0) + 1

        multi_region = len(regions) > 1
        is_susceptible = False

        if multi_region:
            for region, count in regions.items():
                if count >= (total_voters // 2) + 1:
                    scenarios.append(
                        f"Region '{region}' holds a majority ({count}/{total_voters}). "
                        "Partition isolating other regions may not cause split-brain."
                    )
                else:
                    scenarios.append(
                        f"Region '{region}' has {count}/{total_voters} voters. "
                        "May form minority partition."
                    )
            # Check if any single-region partition can form dual quorums
            max_region_size = max(regions.values()) if regions else 0
            remaining = total_voters - max_region_size
            if max_region_size >= (total_voters // 2) + 1 and remaining >= (
                total_voters // 2
            ) + 1:
                is_susceptible = True
                dual_leader_prob = 0.3
        else:
            scenarios.append(
                "All voters in same region. Inter-region split-brain not applicable."
            )

        if total_voters <= 2:
            is_susceptible = True
            dual_leader_prob = max(dual_leader_prob, 0.5)
            scenarios.append(
                "Two or fewer voters: any partition risks split-brain."
            )

        if total_voters % 2 == 0 and total_voters > 2:
            is_susceptible = True
            dual_leader_prob = max(dual_leader_prob, 0.2)
            scenarios.append(
                "Even voter count: symmetric partition can form two equal halves."
            )

        # Prevention mechanisms
        if cluster.protocol == ConsensusProtocol.RAFT:
            prevention.append("Raft leader lease prevents stale leader reads.")
            if cluster.pre_vote_enabled:
                prevention.append(
                    "Pre-vote enabled: reduces disruptive elections from "
                    "partitioned nodes."
                )
                dual_leader_prob *= 0.5
        elif cluster.protocol == ConsensusProtocol.PBFT:
            prevention.append(
                "PBFT tolerates Byzantine faults including equivocation."
            )
            dual_leader_prob *= 0.3
        elif cluster.protocol == ConsensusProtocol.ZAB:
            prevention.append(
                "ZAB epoch-based leader election prevents stale leaders."
            )
        elif cluster.protocol == ConsensusProtocol.PAXOS:
            prevention.append(
                "Paxos ballot numbers ensure only one proposer wins per round."
            )

        has_witness = any(n.role == NodeRole.WITNESS for n in cluster.nodes)
        if has_witness:
            prevention.append(
                "Witness node(s) provide tie-breaking vote without full data."
            )
            dual_leader_prob *= 0.7

        detection_time = cluster.election_timeout_ms * 2
        resolution_time = cluster.election_timeout_ms * 3 + 100.0

        if not is_susceptible:
            risk = RiskLevel.LOW
        elif dual_leader_prob > 0.3:
            risk = RiskLevel.HIGH
        elif dual_leader_prob > 0.1:
            risk = RiskLevel.MEDIUM
        else:
            risk = RiskLevel.LOW

        recs: list[str] = []
        if is_susceptible:
            recs.append("Use odd number of voters to avoid symmetric partitions.")
        if not cluster.pre_vote_enabled and cluster.protocol == ConsensusProtocol.RAFT:
            recs.append("Enable pre-vote to reduce disruptive elections.")
        if not has_witness and total_voters % 2 == 0:
            recs.append(
                "Add a witness node to break ties in even-sized clusters."
            )
        if multi_region and not has_witness:
            recs.append(
                "Place a witness in a third region for cross-region tie-breaking."
            )

        return SplitBrainAnalysis(
            cluster_id=cluster.cluster_id,
            is_susceptible=is_susceptible,
            risk_level=risk,
            partition_scenarios=scenarios,
            prevention_mechanisms=prevention,
            estimated_detection_time_ms=detection_time,
            estimated_resolution_time_ms=resolution_time,
            dual_leader_probability=round(dual_leader_prob, 4),
            recommendations=recs,
        )

    # -- Leader Election Impact ---------------------------------------------

    def analyze_leader_election(
        self, cluster: ConsensusCluster
    ) -> LeaderElectionImpact:
        """Model the impact of leader election failure."""
        leader_id = ""
        candidates = 0
        for n in cluster.nodes:
            if n.role == NodeRole.LEADER:
                leader_id = n.node_id
            if n.role in (NodeRole.FOLLOWER, NodeRole.CANDIDATE) and n.is_healthy:
                candidates += 1

        timeout = cluster.election_timeout_ms
        # Estimated write downtime: at least one election timeout + network RTT
        avg_latency = self._avg_node_latency(cluster)
        write_unavail = timeout + avg_latency * 2

        # Split vote risk increases with more candidates
        if candidates <= 1:
            split_vote_risk = 0.0
        elif candidates == 2:
            split_vote_risk = 0.1
        else:
            split_vote_risk = min(0.8, 0.1 * candidates)

        # Pre-vote reduces disruption
        pre_vote_helps = cluster.pre_vote_enabled
        if pre_vote_helps:
            write_unavail *= 0.7
            split_vote_risk *= 0.5

        estimated_downtime = write_unavail * (1.0 + split_vote_risk)

        # Read availability depends on protocol
        read_avail = cluster.protocol in (
            ConsensusProtocol.RAFT,
            ConsensusProtocol.ZAB,
        )

        if estimated_downtime > 5000:
            risk = RiskLevel.CRITICAL
        elif estimated_downtime > 2000:
            risk = RiskLevel.HIGH
        elif estimated_downtime > 500:
            risk = RiskLevel.MEDIUM
        else:
            risk = RiskLevel.LOW

        recs: list[str] = []
        if not pre_vote_helps and cluster.protocol == ConsensusProtocol.RAFT:
            recs.append("Enable pre-vote to reduce election disruption.")
        if candidates == 0:
            recs.append(
                "No healthy candidates available. Recovery requires manual intervention."
            )
            risk = RiskLevel.CRITICAL
        if split_vote_risk > 0.3:
            recs.append(
                "High split-vote risk. Randomize election timeouts to reduce contention."
            )
        if timeout > 500:
            recs.append(
                "Election timeout is high. Consider reducing for faster failover."
            )

        return LeaderElectionImpact(
            cluster_id=cluster.cluster_id,
            current_leader_id=leader_id,
            election_timeout_ms=timeout,
            estimated_downtime_ms=round(estimated_downtime, 2),
            write_unavailability_ms=round(write_unavail, 2),
            read_availability_during_election=read_avail,
            candidate_count=candidates,
            risk_of_split_vote=round(split_vote_risk, 4),
            pre_vote_reduces_disruption=pre_vote_helps,
            risk_level=risk,
            recommendations=recs,
        )

    # -- Network Partition Tolerance ----------------------------------------

    def analyze_partition_tolerance(
        self,
        cluster: ConsensusCluster,
        partition_type: PartitionType = PartitionType.SYMMETRIC,
        isolated_node_ids: list[str] | None = None,
    ) -> PartitionToleranceResult:
        """Analyze behavior under a network partition scenario."""
        total_voters, _, _ = self._count_voters(cluster)
        quorum_size = self._quorum_size(cluster)

        if isolated_node_ids:
            isolated_count = 0
            for n in cluster.nodes:
                if n.node_id in isolated_node_ids and n.role not in (
                    NodeRole.OBSERVER,
                    NodeRole.LEARNER,
                ):
                    isolated_count += 1
            surviving = total_voters - isolated_count
        elif partition_type == PartitionType.TOTAL:
            surviving = 0
            isolated_count = total_voters
        elif partition_type == PartitionType.PARTIAL:
            isolated_count = 1
            surviving = total_voters - 1
        else:
            # Symmetric: split roughly in half
            isolated_count = total_voters // 2
            surviving = total_voters - isolated_count

        maintains_quorum = surviving >= quorum_size

        # Byzantine fault tolerance
        if cluster.protocol == ConsensusProtocol.PBFT:
            max_byz = (total_voters - 1) // 3
        else:
            max_byz = 0
        bft = max_byz

        safety = True
        liveness = maintains_quorum
        if partition_type == PartitionType.ASYMMETRIC:
            safety = cluster.protocol in (
                ConsensusProtocol.RAFT,
                ConsensusProtocol.PBFT,
            )

        if not maintains_quorum:
            risk = RiskLevel.CRITICAL
        elif surviving == quorum_size:
            risk = RiskLevel.HIGH
        elif isolated_count > 0:
            risk = RiskLevel.MEDIUM
        else:
            risk = RiskLevel.LOW

        recs: list[str] = []
        if not maintains_quorum:
            recs.append(
                f"Quorum lost ({surviving}/{quorum_size} voters). "
                "System cannot make progress."
            )
        if not safety:
            recs.append(
                "Safety may be compromised under asymmetric partition. "
                "Consider using PBFT or Raft with lease."
            )
        if max_byz == 0:
            recs.append(
                f"{cluster.protocol.value} does not tolerate Byzantine faults. "
                "Use PBFT for Byzantine tolerance."
            )
        if total_voters < 5 and isolated_count > 1:
            recs.append(
                "Small cluster size limits partition tolerance. "
                "Consider expanding to 5+ voters."
            )

        return PartitionToleranceResult(
            cluster_id=cluster.cluster_id,
            partition_type=partition_type,
            surviving_partition_size=surviving,
            isolated_partition_size=isolated_count,
            maintains_quorum=maintains_quorum,
            byzantine_fault_tolerance=bft,
            max_byzantine_nodes=max_byz,
            safety_preserved=safety,
            liveness_preserved=liveness,
            risk_level=risk,
            recommendations=recs,
        )

    # -- Consensus Latency Modeling -----------------------------------------

    def model_consensus_latency(
        self, cluster: ConsensusCluster
    ) -> ConsensusLatencyModel:
        """Model commit latency under various failure scenarios."""
        base = _PROTOCOL_BASE_LATENCY.get(cluster.protocol, 5.0)
        total_voters, healthy_voters, _ = self._count_voters(cluster)
        quorum = self._quorum_size(cluster)
        avg_latency = self._avg_node_latency(cluster)

        # Normal: fastest quorum response
        node_latencies = sorted(
            n.latency_ms
            for n in cluster.nodes
            if n.role not in (NodeRole.OBSERVER, NodeRole.LEARNER)
            and n.is_healthy
        )
        if len(node_latencies) >= quorum:
            quorum_latency = node_latencies[quorum - 1]
        elif node_latencies:
            quorum_latency = node_latencies[-1]
        else:
            quorum_latency = avg_latency

        normal = base + quorum_latency

        # Cross-region latency
        regions = set()
        for n in cluster.nodes:
            if n.region:
                regions.add(n.region)
        if len(regions) > 1:
            cross_region = base + _REGION_LATENCY["cross_region"]
        else:
            cross_region = normal

        # One-node failure: remove fastest node, take next quorum
        one_fail = normal * 1.2 if healthy_voters > quorum else normal * 3.0

        # Two-node failure
        if healthy_voters > quorum + 1:
            two_fail = normal * 1.5
        elif healthy_voters > quorum:
            two_fail = normal * 2.0
        else:
            two_fail = normal * 5.0  # likely no quorum

        # Degraded (at quorum boundary)
        degraded = normal * 1.8

        # Leader in minority (no progress)
        leader_minority = normal * 10.0

        p50 = normal
        p99 = max(one_fail, cross_region) * 1.5

        if p99 > 500:
            risk = RiskLevel.HIGH
        elif p99 > 200:
            risk = RiskLevel.MEDIUM
        else:
            risk = RiskLevel.LOW

        recs: list[str] = []
        if cross_region > normal * 5:
            recs.append(
                "Cross-region latency significantly impacts consensus. "
                "Consider placing quorum in a single region."
            )
        if p99 > 500:
            recs.append(
                f"p99 latency of {p99:.0f}ms exceeds 500ms target. "
                "Optimize node placement or batch size."
            )
        if total_voters > 5:
            recs.append(
                "Large voter set increases commit latency. "
                "Use observers for read scaling instead."
            )

        return ConsensusLatencyModel(
            cluster_id=cluster.cluster_id,
            normal_commit_latency_ms=round(normal, 2),
            degraded_commit_latency_ms=round(degraded, 2),
            one_node_failure_latency_ms=round(one_fail, 2),
            two_node_failure_latency_ms=round(two_fail, 2),
            cross_region_latency_ms=round(cross_region, 2),
            leader_in_minority_latency_ms=round(leader_minority, 2),
            p50_latency_ms=round(p50, 2),
            p99_latency_ms=round(p99, 2),
            risk_level=risk,
            recommendations=recs,
        )

    # -- Quorum Loss Recovery -----------------------------------------------

    def estimate_quorum_recovery(
        self,
        cluster: ConsensusCluster,
        nodes_lost: int = 1,
        snapshot_size_mb: float = _DEFAULT_SNAPSHOT_SIZE_MB,
    ) -> QuorumRecoveryEstimate:
        """Estimate recovery time after quorum loss."""
        total_voters, healthy_voters, _ = self._count_voters(cluster)
        quorum = self._quorum_size(cluster)

        nodes_to_recover = max(0, quorum - (healthy_voters - nodes_lost))
        if nodes_to_recover <= 0:
            nodes_to_recover = 0

        # Snapshot transfer time
        snapshot_time = snapshot_size_mb * _SNAPSHOT_TRANSFER_MS_PER_MB

        # Log replay time
        leader_index = 0
        for n in cluster.nodes:
            if n.role == NodeRole.LEADER:
                leader_index = n.log_index
                break
        log_entries_to_replay = max(0, leader_index - cluster.snapshot_threshold)
        log_replay_time = log_entries_to_replay * _LOG_REPLAY_MS_PER_ENTRY

        # Leader election time
        election_time = cluster.election_timeout_ms * 2.0

        per_node_recovery = snapshot_time + log_replay_time
        total = (per_node_recovery * max(1, nodes_to_recover)) + election_time

        data_at_risk = healthy_voters - nodes_lost < quorum

        if total > 60000:
            risk = RiskLevel.CRITICAL
        elif total > 30000:
            risk = RiskLevel.HIGH
        elif total > 10000:
            risk = RiskLevel.MEDIUM
        else:
            risk = RiskLevel.LOW

        recs: list[str] = []
        if data_at_risk:
            recs.append(
                "Data at risk: insufficient healthy voters for quorum. "
                "Prioritize node recovery."
            )
        if snapshot_size_mb > 100:
            recs.append(
                "Large snapshots slow recovery. Consider compaction or "
                "incremental snapshots."
            )
        if log_entries_to_replay > 50000:
            recs.append(
                "Large log replay needed. Lower snapshot threshold to reduce "
                "recovery time."
            )
        if nodes_to_recover > 1:
            recs.append(
                "Multiple nodes need recovery. Consider parallel recovery "
                "to reduce total time."
            )

        return QuorumRecoveryEstimate(
            cluster_id=cluster.cluster_id,
            nodes_to_recover=nodes_to_recover,
            estimated_recovery_time_ms=round(total, 2),
            snapshot_transfer_time_ms=round(snapshot_time, 2),
            log_replay_time_ms=round(log_replay_time, 2),
            leader_election_time_ms=round(election_time, 2),
            total_unavailability_ms=round(total, 2),
            data_at_risk=data_at_risk,
            risk_level=risk,
            recommendations=recs,
        )

    # -- Write Availability -------------------------------------------------

    def assess_write_availability(
        self,
        cluster: ConsensusCluster,
        failed_node_ids: list[str] | None = None,
    ) -> WriteAvailabilityAssessment:
        """Assess write availability during partial failures."""
        total_voters, healthy_voters, _ = self._count_voters(cluster)
        quorum = self._quorum_size(cluster)

        if failed_node_ids:
            failed_count = 0
            for n in cluster.nodes:
                if n.node_id in failed_node_ids and n.role not in (
                    NodeRole.OBSERVER,
                    NodeRole.LEARNER,
                ):
                    failed_count += 1
        else:
            failed_count = total_voters - healthy_voters

        effective_voters = total_voters - failed_count
        writes_available = effective_voters >= quorum

        if writes_available:
            throughput_factor = effective_voters / max(1, total_voters)
            # Latency increases as we approach quorum boundary
            margin = effective_voters - quorum
            if margin == 0:
                latency_factor = 2.0
            elif margin == 1:
                latency_factor = 1.3
            else:
                latency_factor = 1.0
        else:
            throughput_factor = 0.0
            latency_factor = float("inf")

        durability = effective_voters / max(1, total_voters)

        if not writes_available:
            risk = RiskLevel.CRITICAL
        elif throughput_factor < 0.5:
            risk = RiskLevel.HIGH
        elif throughput_factor < 0.8:
            risk = RiskLevel.MEDIUM
        else:
            risk = RiskLevel.LOW

        recs: list[str] = []
        if not writes_available:
            recs.append(
                f"Writes unavailable: {effective_voters}/{quorum} voters. "
                "Recover nodes to restore quorum."
            )
        if durability < 0.5:
            recs.append(
                "Durability significantly reduced. Data loss risk is elevated."
            )
        if failed_count > 0 and writes_available:
            recs.append(
                f"{failed_count} voter(s) down. Writes still available but "
                "fault tolerance is reduced."
            )

        return WriteAvailabilityAssessment(
            cluster_id=cluster.cluster_id,
            total_nodes=total_voters,
            failed_nodes=failed_count,
            writes_available=writes_available,
            write_throughput_factor=round(throughput_factor, 4),
            latency_increase_factor=round(latency_factor, 4),
            durability_factor=round(durability, 4),
            risk_level=risk,
            recommendations=recs,
        )

    # -- CAP Theorem Scoring ------------------------------------------------

    def score_cap_tradeoff(self, cluster: ConsensusCluster) -> CAPScore:
        """Score the CAP theorem trade-offs for the cluster."""
        protocol = cluster.protocol
        total_voters, healthy_voters, _ = self._count_voters(cluster)

        # Consistency score
        if protocol == ConsensusProtocol.PBFT:
            consistency = 95.0
        elif protocol == ConsensusProtocol.RAFT:
            consistency = 90.0
        elif protocol == ConsensusProtocol.ZAB:
            consistency = 88.0
        elif protocol == ConsensusProtocol.PAXOS:
            consistency = 85.0
        else:
            consistency = 80.0

        # Availability score - based on quorum health
        quorum = self._quorum_size(cluster)
        if healthy_voters >= quorum + 2:
            availability = 95.0
        elif healthy_voters >= quorum + 1:
            availability = 80.0
        elif healthy_voters >= quorum:
            availability = 60.0
        else:
            availability = 20.0

        # Partition tolerance score
        regions = set()
        for n in cluster.nodes:
            if n.region:
                regions.add(n.region)
        multi_region = len(regions) > 1

        if protocol == ConsensusProtocol.PBFT:
            partition = 90.0
        elif multi_region and total_voters >= 5:
            partition = 85.0
        elif total_voters >= 5:
            partition = 75.0
        elif total_voters >= 3:
            partition = 60.0
        else:
            partition = 30.0

        # Determine primary preference
        scores = {
            CAPPreference.CONSISTENCY: consistency,
            CAPPreference.AVAILABILITY: availability,
            CAPPreference.PARTITION_TOLERANCE: partition,
        }
        primary = max(scores, key=scores.get)  # type: ignore[arg-type]

        desc = self._cap_description(protocol, primary)

        recs: list[str] = []
        if availability < 60:
            recs.append(
                "Low availability score. Add healthy voters to improve."
            )
        if partition < 60:
            recs.append(
                "Low partition tolerance. Deploy across multiple regions."
            )
        if consistency < 85:
            recs.append(
                "Moderate consistency. Ensure linearizable reads if required."
            )

        return CAPScore(
            cluster_id=cluster.cluster_id,
            consistency_score=round(consistency, 2),
            availability_score=round(availability, 2),
            partition_tolerance_score=round(partition, 2),
            primary_preference=primary,
            trade_off_description=desc,
            recommendations=recs,
        )

    # -- Protocol Comparison ------------------------------------------------

    def compare_protocols(
        self, workload: WorkloadType
    ) -> ProtocolComparison:
        """Compare consensus protocols for a given workload type."""
        rankings: list[ProtocolRanking] = []
        for proto in ConsensusProtocol:
            base_latency = _PROTOCOL_BASE_LATENCY[proto]
            throughput = _PROTOCOL_THROUGHPUT[proto]
            complexity = _PROTOCOL_COMPLEXITY[proto]

            # Latency score (lower latency = higher score)
            latency_score = max(0.0, 100.0 - base_latency * 5)

            # Throughput score
            throughput_score = throughput * 100.0

            # Fault tolerance score
            if _PROTOCOL_BFT[proto]:
                ft_score = 95.0
            else:
                ft_score = 70.0

            # Complexity score (lower complexity = higher score)
            complexity_score = max(0.0, 100.0 - complexity * 10)

            # Weight by workload
            if workload == WorkloadType.LATENCY_SENSITIVE:
                overall = (
                    latency_score * 0.5
                    + throughput_score * 0.2
                    + ft_score * 0.2
                    + complexity_score * 0.1
                )
            elif workload == WorkloadType.THROUGHPUT_OPTIMIZED:
                overall = (
                    latency_score * 0.2
                    + throughput_score * 0.5
                    + ft_score * 0.2
                    + complexity_score * 0.1
                )
            elif workload == WorkloadType.WRITE_HEAVY:
                overall = (
                    latency_score * 0.3
                    + throughput_score * 0.4
                    + ft_score * 0.2
                    + complexity_score * 0.1
                )
            elif workload == WorkloadType.READ_HEAVY:
                overall = (
                    latency_score * 0.3
                    + throughput_score * 0.3
                    + ft_score * 0.2
                    + complexity_score * 0.2
                )
            else:  # BALANCED
                overall = (
                    latency_score * 0.25
                    + throughput_score * 0.25
                    + ft_score * 0.25
                    + complexity_score * 0.25
                )

            rankings.append(
                ProtocolRanking(
                    protocol=proto,
                    latency_score=round(latency_score, 2),
                    throughput_score=round(throughput_score, 2),
                    fault_tolerance_score=round(ft_score, 2),
                    complexity_score=round(complexity_score, 2),
                    overall_score=round(overall, 2),
                )
            )

        rankings.sort(key=lambda r: r.overall_score, reverse=True)
        best = rankings[0].protocol

        rationale = self._comparison_rationale(workload, best)

        recs: list[str] = []
        if workload == WorkloadType.LATENCY_SENSITIVE:
            recs.append("For latency-sensitive workloads, minimize voter count.")
        if workload == WorkloadType.THROUGHPUT_OPTIMIZED:
            recs.append(
                "For throughput, use batching and pipelining features."
            )
        recs.append(f"Best fit: {best.value} for {workload.value} workloads.")

        return ProtocolComparison(
            workload=workload,
            rankings=rankings,
            best_fit=best,
            rationale=rationale,
            recommendations=recs,
        )

    # -- Membership Change Impact -------------------------------------------

    def analyze_membership_change(
        self,
        cluster: ConsensusCluster,
        change_type: MembershipChangeType,
        node_id: str = "",
    ) -> MembershipChangeImpact:
        """Assess the impact of a voter membership change."""
        total_voters, healthy_voters, _ = self._count_voters(cluster)
        quorum_before = self._quorum_size(cluster)
        ft_before = total_voters - quorum_before

        # Calculate after-change values
        if change_type in (
            MembershipChangeType.ADD_VOTER,
            MembershipChangeType.PROMOTE_OBSERVER,
        ):
            voters_after = total_voters + 1
        elif change_type in (
            MembershipChangeType.REMOVE_VOTER,
            MembershipChangeType.DEMOTE_VOTER,
        ):
            voters_after = max(0, total_voters - 1)
        else:
            # ADD_OBSERVER, REMOVE_OBSERVER don't affect voter count
            voters_after = total_voters

        if cluster.protocol == ConsensusProtocol.PBFT:
            quorum_after = (2 * voters_after // 3) + 1
        else:
            quorum_after = (voters_after // 2) + 1
        ft_after = voters_after - quorum_after

        # Joint consensus needed for safety
        requires_joint = change_type in (
            MembershipChangeType.ADD_VOTER,
            MembershipChangeType.REMOVE_VOTER,
            MembershipChangeType.PROMOTE_OBSERVER,
            MembershipChangeType.DEMOTE_VOTER,
        )

        # Risk during transition
        if ft_after < ft_before:
            transition_risk = RiskLevel.MEDIUM
        elif ft_after <= 0:
            transition_risk = RiskLevel.HIGH
        else:
            transition_risk = RiskLevel.LOW

        if voters_after < 3 and change_type in (
            MembershipChangeType.REMOVE_VOTER,
            MembershipChangeType.DEMOTE_VOTER,
        ):
            transition_risk = RiskLevel.CRITICAL

        # Transition time estimate
        transition_time = cluster.election_timeout_ms * 2
        if requires_joint:
            transition_time += cluster.election_timeout_ms

        recs: list[str] = []
        if ft_after < ft_before:
            recs.append(
                f"Fault tolerance decreases from {ft_before} to {ft_after}. "
                "Monitor closely during transition."
            )
        if requires_joint:
            recs.append(
                "Joint consensus required. Ensure cluster is healthy "
                "before initiating change."
            )
        if voters_after % 2 == 0:
            recs.append(
                "Result is even voter count. Consider adding another voter."
            )
        if change_type == MembershipChangeType.REMOVE_VOTER and voters_after < 3:
            recs.append(
                "Cluster will have fewer than 3 voters. No fault tolerance."
            )

        return MembershipChangeImpact(
            cluster_id=cluster.cluster_id,
            change_type=change_type,
            node_id=node_id,
            quorum_before=quorum_before,
            quorum_after=quorum_after,
            fault_tolerance_before=ft_before,
            fault_tolerance_after=ft_after,
            requires_joint_consensus=requires_joint,
            risk_during_transition=transition_risk,
            estimated_transition_time_ms=round(transition_time, 2),
            recommendations=recs,
        )

    # -- Log Replication Lag ------------------------------------------------

    def assess_log_replication_lag(
        self, cluster: ConsensusCluster
    ) -> LogReplicationLag:
        """Assess log replication lag across cluster followers."""
        leader_index = 0
        for n in cluster.nodes:
            if n.role == NodeRole.LEADER:
                leader_index = n.log_index
                break

        followers = [
            n
            for n in cluster.nodes
            if n.role in (NodeRole.FOLLOWER, NodeRole.CANDIDATE)
        ]

        if not followers:
            return LogReplicationLag(
                cluster_id=cluster.cluster_id,
                leader_log_index=leader_index,
                risk_level=RiskLevel.LOW,
                recommendations=["No followers found in cluster."],
            )

        follower_indices = [f.log_index for f in followers]
        min_idx = min(follower_indices)
        max_idx = max(follower_indices)

        lags = [leader_index - f.log_index for f in followers]
        avg_lag = sum(lags) / len(lags) if lags else 0.0
        max_lag = max(lags) if lags else 0

        # Estimate time lag based on heartbeat interval
        max_lag_ms = max_lag * cluster.heartbeat_interval_ms * 0.1

        lagging = [
            f.node_id
            for f in followers
            if leader_index - f.log_index > 100
        ]

        if max_lag > 10000:
            risk = RiskLevel.CRITICAL
        elif max_lag > 1000:
            risk = RiskLevel.HIGH
        elif max_lag > 100:
            risk = RiskLevel.MEDIUM
        else:
            risk = RiskLevel.LOW

        recs: list[str] = []
        if max_lag > 1000:
            recs.append(
                f"Max lag of {max_lag} entries is excessive. "
                "Check slow followers or network issues."
            )
        if lagging:
            recs.append(
                f"Lagging nodes: {', '.join(lagging)}. "
                "May impact data durability on failover."
            )
        if max_lag > cluster.snapshot_threshold:
            recs.append(
                "Lag exceeds snapshot threshold. Follower may need full "
                "snapshot transfer to catch up."
            )

        return LogReplicationLag(
            cluster_id=cluster.cluster_id,
            leader_log_index=leader_index,
            min_follower_index=min_idx,
            max_follower_index=max_idx,
            avg_lag_entries=round(avg_lag, 2),
            max_lag_entries=max_lag,
            max_lag_ms=round(max_lag_ms, 2),
            lagging_nodes=lagging,
            risk_level=risk,
            recommendations=recs,
        )

    # -- Witness/Observer Effectiveness -------------------------------------

    def evaluate_witness_effectiveness(
        self, cluster: ConsensusCluster
    ) -> WitnessEffectiveness:
        """Evaluate the effectiveness of witness and observer nodes."""
        witnesses = [
            n for n in cluster.nodes if n.role == NodeRole.WITNESS
        ]
        observers = [
            n for n in cluster.nodes
            if n.role in (NodeRole.OBSERVER, NodeRole.LEARNER)
        ]
        total_voters, _, _ = self._count_voters(cluster)

        witness_count = len(witnesses)
        observer_count = len(observers)

        # Witnesses contribute to quorum
        quorum_contribution = witness_count > 0

        # Failover speed improvement
        if witness_count > 0:
            failover_improvement = cluster.election_timeout_ms * 0.3
        else:
            failover_improvement = 0.0

        # Cost efficiency: witnesses use less resources than full replicas
        total_nodes = len(cluster.nodes)
        if total_nodes > 0:
            lightweight_ratio = (witness_count + observer_count) / total_nodes
            cost_efficiency = lightweight_ratio * 100.0
        else:
            cost_efficiency = 0.0

        # Split-brain prevention
        split_brain_prevention = (
            witness_count > 0
            and total_voters % 2 == 1
        )

        if witness_count == 0 and observer_count == 0:
            risk = RiskLevel.MEDIUM
        elif witness_count > 0 and quorum_contribution:
            risk = RiskLevel.LOW
        else:
            risk = RiskLevel.LOW

        recs: list[str] = []
        if witness_count == 0 and total_voters % 2 == 0:
            recs.append(
                "Add a witness node to break ties in even-sized cluster."
            )
        if observer_count == 0 and total_voters >= 5:
            recs.append(
                "Add observer nodes for read scaling without quorum impact."
            )
        if witness_count > 1:
            recs.append(
                "Multiple witnesses provide diminishing returns. "
                "One witness is typically sufficient."
            )
        healthy_witnesses = sum(1 for w in witnesses if w.is_healthy)
        if witness_count > 0 and healthy_witnesses == 0:
            recs.append(
                "All witness nodes are unhealthy. Restore witness availability."
            )
            risk = RiskLevel.HIGH

        return WitnessEffectiveness(
            cluster_id=cluster.cluster_id,
            witness_count=witness_count,
            observer_count=observer_count,
            quorum_contribution=quorum_contribution,
            failover_speed_improvement_ms=round(failover_improvement, 2),
            cost_efficiency_ratio=round(cost_efficiency, 2),
            split_brain_prevention=split_brain_prevention,
            risk_level=risk,
            recommendations=recs,
        )

    # -- Comprehensive Report -----------------------------------------------

    def generate_report(self) -> ConsensusAnalysisReport:
        """Generate a comprehensive analysis report for all registered clusters."""
        now = datetime.now(timezone.utc).isoformat()
        report = ConsensusAnalysisReport(
            analyzed_at=now,
            clusters_analyzed=len(self._clusters),
        )

        all_risks: list[RiskLevel] = []
        all_recs: list[str] = []

        for cluster in self._clusters:
            qa = self.analyze_quorum(cluster)
            report.quorum_analyses.append(qa)
            all_risks.append(qa.risk_level)
            all_recs.extend(qa.recommendations)

            sba = self.analyze_split_brain(cluster)
            report.split_brain_analyses.append(sba)
            all_risks.append(sba.risk_level)
            all_recs.extend(sba.recommendations)

            lei = self.analyze_leader_election(cluster)
            report.leader_election_impacts.append(lei)
            all_risks.append(lei.risk_level)
            all_recs.extend(lei.recommendations)

            ptr = self.analyze_partition_tolerance(cluster)
            report.partition_tolerance_results.append(ptr)
            all_risks.append(ptr.risk_level)
            all_recs.extend(ptr.recommendations)

            clm = self.model_consensus_latency(cluster)
            report.latency_models.append(clm)
            all_risks.append(clm.risk_level)
            all_recs.extend(clm.recommendations)

            qre = self.estimate_quorum_recovery(cluster)
            report.recovery_estimates.append(qre)
            all_risks.append(qre.risk_level)
            all_recs.extend(qre.recommendations)

            wa = self.assess_write_availability(cluster)
            report.write_availability.append(wa)
            all_risks.append(wa.risk_level)
            all_recs.extend(wa.recommendations)

            cap = self.score_cap_tradeoff(cluster)
            report.cap_scores.append(cap)
            all_recs.extend(cap.recommendations)

            lrl = self.assess_log_replication_lag(cluster)
            report.log_replication_lags.append(lrl)
            all_risks.append(lrl.risk_level)
            all_recs.extend(lrl.recommendations)

            we = self.evaluate_witness_effectiveness(cluster)
            report.witness_evaluations.append(we)
            all_risks.append(we.risk_level)
            all_recs.extend(we.recommendations)

        # Overall health
        risk_weights = {
            RiskLevel.LOW: 0,
            RiskLevel.MEDIUM: 10,
            RiskLevel.HIGH: 25,
            RiskLevel.CRITICAL: 50,
        }
        if all_risks:
            penalty = sum(risk_weights.get(r, 0) for r in all_risks) / len(
                all_risks
            )
            report.overall_health = round(max(0.0, 100.0 - penalty * 3), 2)
        else:
            report.overall_health = 100.0

        # Overall risk
        if any(r == RiskLevel.CRITICAL for r in all_risks):
            report.risk_level = RiskLevel.CRITICAL
        elif any(r == RiskLevel.HIGH for r in all_risks):
            report.risk_level = RiskLevel.HIGH
        elif any(r == RiskLevel.MEDIUM for r in all_risks):
            report.risk_level = RiskLevel.MEDIUM
        else:
            report.risk_level = RiskLevel.LOW

        # Deduplicate recommendations
        seen: set[str] = set()
        for rec in all_recs:
            if rec not in seen:
                seen.add(rec)
                report.recommendations.append(rec)

        return report

    # -- Graph-based helpers ------------------------------------------------

    def detect_consensus_clusters_from_graph(
        self,
        protocol: ConsensusProtocol = ConsensusProtocol.RAFT,
        component_type: ComponentType = ComponentType.DATABASE,
    ) -> list[ConsensusCluster]:
        """Auto-detect potential consensus clusters from the infrastructure graph.

        Groups components of the specified type that are interconnected and
        creates a cluster configuration for each group. Useful when explicit
        cluster registration is not available.
        """
        clusters: list[ConsensusCluster] = []
        visited: set[str] = set()

        target_components = [
            c
            for c in self._graph.components.values()
            if c.type == component_type
        ]

        for comp in target_components:
            if comp.id in visited:
                continue
            # BFS to find connected components of the same type
            group: list[Component] = []
            queue = [comp.id]
            while queue:
                cid = queue.pop(0)
                if cid in visited:
                    continue
                c = self._graph.get_component(cid)
                if c is None:
                    continue
                if c.type != component_type:
                    continue
                visited.add(cid)
                group.append(c)
                # Check both directions
                for dep in self._graph.get_dependencies(cid):
                    if dep.type == component_type and dep.id not in visited:
                        queue.append(dep.id)
                for dep in self._graph.get_dependents(cid):
                    if dep.type == component_type and dep.id not in visited:
                        queue.append(dep.id)

            if len(group) >= 2:
                nodes: list[ConsensusNode] = []
                for i, g in enumerate(group):
                    role = NodeRole.LEADER if i == 0 else NodeRole.FOLLOWER
                    nodes.append(
                        ConsensusNode(
                            node_id=f"{g.id}_node",
                            component_id=g.id,
                            role=role,
                            region=g.region.region,
                            availability_zone=g.region.availability_zone,
                            is_healthy=g.health.value == "healthy",
                        )
                    )
                cluster = ConsensusCluster(
                    cluster_id=f"auto_{group[0].id}_cluster",
                    protocol=protocol,
                    nodes=nodes,
                )
                clusters.append(cluster)

        return clusters

    # -- Private helpers ----------------------------------------------------

    def _quorum_size(self, cluster: ConsensusCluster) -> int:
        """Calculate quorum size for the cluster."""
        total_voters, _, _ = self._count_voters(cluster)
        if cluster.protocol == ConsensusProtocol.PBFT:
            return (2 * total_voters // 3) + 1
        return (total_voters // 2) + 1

    def _avg_node_latency(self, cluster: ConsensusCluster) -> float:
        """Average latency of healthy voter nodes."""
        latencies = [
            n.latency_ms
            for n in cluster.nodes
            if n.is_healthy
            and n.role not in (NodeRole.OBSERVER, NodeRole.LEARNER)
        ]
        if not latencies:
            return 10.0
        return sum(latencies) / len(latencies)

    @staticmethod
    def _cap_description(
        protocol: ConsensusProtocol, primary: CAPPreference
    ) -> str:
        """Generate a human-readable CAP trade-off description."""
        descs = {
            (ConsensusProtocol.RAFT, CAPPreference.CONSISTENCY): (
                "Raft prioritizes consistency (CP). Writes require majority "
                "quorum; partitioned minorities cannot serve writes."
            ),
            (ConsensusProtocol.RAFT, CAPPreference.AVAILABILITY): (
                "Raft cluster has high availability due to healthy quorum margin."
            ),
            (ConsensusProtocol.PAXOS, CAPPreference.CONSISTENCY): (
                "Paxos provides strong consistency (CP) with flexible quorum "
                "configurations."
            ),
            (ConsensusProtocol.ZAB, CAPPreference.CONSISTENCY): (
                "ZAB (ZooKeeper) provides consistency with ordered broadcasts."
            ),
            (ConsensusProtocol.PBFT, CAPPreference.CONSISTENCY): (
                "PBFT provides Byzantine fault tolerance with strong consistency."
            ),
            (ConsensusProtocol.PBFT, CAPPreference.PARTITION_TOLERANCE): (
                "PBFT excels at partition tolerance with Byzantine safety."
            ),
        }
        key = (protocol, primary)
        if key in descs:
            return descs[key]
        return (
            f"{protocol.value} with primary emphasis on "
            f"{primary.value.replace('_', ' ')}."
        )

    @staticmethod
    def _comparison_rationale(
        workload: WorkloadType, best: ConsensusProtocol
    ) -> str:
        """Generate a rationale for protocol recommendation."""
        reasons = {
            (WorkloadType.READ_HEAVY, ConsensusProtocol.RAFT): (
                "Raft supports follower reads and has simple leader-based "
                "architecture ideal for read-heavy workloads."
            ),
            (WorkloadType.WRITE_HEAVY, ConsensusProtocol.RAFT): (
                "Raft's batched log replication efficiently handles "
                "write-heavy workloads with low complexity."
            ),
            (WorkloadType.LATENCY_SENSITIVE, ConsensusProtocol.RAFT): (
                "Raft's single-round-trip commits provide lowest latency "
                "for latency-sensitive workloads."
            ),
            (WorkloadType.THROUGHPUT_OPTIMIZED, ConsensusProtocol.RAFT): (
                "Raft's pipelining and batching maximize throughput."
            ),
            (WorkloadType.BALANCED, ConsensusProtocol.RAFT): (
                "Raft provides the best balance of latency, throughput, "
                "and operational simplicity."
            ),
        }
        key = (workload, best)
        if key in reasons:
            return reasons[key]
        return (
            f"{best.value} is recommended for {workload.value} workloads "
            f"based on combined latency, throughput, and fault tolerance scores."
        )
