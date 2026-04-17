# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""Network Partition Simulator.

Simulates and analyzes network partition scenarios with CAP theorem analysis,
split-brain detection, quorum-based decision analysis, partition healing,
leader election behavior, cross-AZ partition modeling, partition tolerance
scoring, network segmentation analysis, partition duration vs data divergence
modeling, and client-side partition handling (timeout, retry, circuit break).

Builds on the lower-level ``network_partition`` module to provide richer,
scenario-oriented simulation and scoring capabilities.
"""

from __future__ import annotations

import logging
import math
from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field

from faultray.model.components import (
    Component,
    ComponentType,
)
from faultray.model.graph import InfraGraph

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class PartitionMode(str, Enum):
    """Partition behaviour modes."""

    FULL = "full"
    ASYMMETRIC = "asymmetric"
    PARTIAL = "partial"
    INTERMITTENT = "intermittent"


class CAPPreference(str, Enum):
    """Service-level CAP preference."""

    CP = "cp"
    AP = "ap"
    BALANCED = "balanced"


class QuorumProtocol(str, Enum):
    """Consensus/quorum protocol family."""

    RAFT = "raft"
    PAXOS = "paxos"
    ZAB = "zab"
    VIEWSTAMPED = "viewstamped"
    NONE = "none"


class HealingPhase(str, Enum):
    """Phases of partition healing."""

    DETECTION = "detection"
    RECONNECTION = "reconnection"
    STATE_SYNC = "state_sync"
    CONFLICT_RESOLUTION = "conflict_resolution"
    LEADER_ELECTION = "leader_election"
    VERIFICATION = "verification"
    COMPLETED = "completed"


class ClientStrategy(str, Enum):
    """Client-side partition handling strategy."""

    TIMEOUT = "timeout"
    RETRY = "retry"
    CIRCUIT_BREAK = "circuit_break"
    FAILOVER = "failover"
    HEDGE = "hedge"


class MitigationAction(str, Enum):
    """Split-brain mitigation action."""

    FENCING = "fencing"
    QUORUM_LEADER = "quorum_leader"
    MANUAL_REVIEW = "manual_review"
    AUTOMATIC_ROLLBACK = "automatic_rollback"
    CRDT_MERGE = "crdt_merge"


# ---------------------------------------------------------------------------
# Severity / weight tables (exported for tests)
# ---------------------------------------------------------------------------

_PARTITION_MODE_SEVERITY: dict[PartitionMode, float] = {
    PartitionMode.FULL: 1.0,
    PartitionMode.ASYMMETRIC: 0.75,
    PartitionMode.PARTIAL: 0.5,
    PartitionMode.INTERMITTENT: 0.6,
}

_CAP_WEIGHTS: dict[CAPPreference, tuple[float, float]] = {
    # (consistency_weight, availability_weight)
    CAPPreference.CP: (1.0, 0.0),
    CAPPreference.AP: (0.0, 1.0),
    CAPPreference.BALANCED: (0.5, 0.5),
}

_QUORUM_ELECTION_BASE_SECONDS: dict[QuorumProtocol, float] = {
    QuorumProtocol.RAFT: 5.0,
    QuorumProtocol.PAXOS: 8.0,
    QuorumProtocol.ZAB: 6.0,
    QuorumProtocol.VIEWSTAMPED: 7.0,
    QuorumProtocol.NONE: 0.0,
}

_CLIENT_STRATEGY_EFFECTIVENESS: dict[ClientStrategy, float] = {
    ClientStrategy.TIMEOUT: 0.3,
    ClientStrategy.RETRY: 0.5,
    ClientStrategy.CIRCUIT_BREAK: 0.8,
    ClientStrategy.FAILOVER: 0.9,
    ClientStrategy.HEDGE: 0.7,
}

_HEALING_PHASE_DURATION_SECONDS: dict[HealingPhase, float] = {
    HealingPhase.DETECTION: 5.0,
    HealingPhase.RECONNECTION: 10.0,
    HealingPhase.STATE_SYNC: 30.0,
    HealingPhase.CONFLICT_RESOLUTION: 45.0,
    HealingPhase.LEADER_ELECTION: 15.0,
    HealingPhase.VERIFICATION: 10.0,
    HealingPhase.COMPLETED: 0.0,
}

_MITIGATION_EFFECTIVENESS: dict[MitigationAction, float] = {
    MitigationAction.FENCING: 0.9,
    MitigationAction.QUORUM_LEADER: 0.85,
    MitigationAction.MANUAL_REVIEW: 0.6,
    MitigationAction.AUTOMATIC_ROLLBACK: 0.75,
    MitigationAction.CRDT_MERGE: 0.8,
}


# ---------------------------------------------------------------------------
# Pydantic result models
# ---------------------------------------------------------------------------


class PartitionScenario(BaseModel):
    """Input configuration for a partition scenario."""

    mode: PartitionMode = PartitionMode.FULL
    affected_component_ids: list[str] = Field(default_factory=list)
    duration_seconds: float = 60.0
    cap_preference: CAPPreference = CAPPreference.AP
    quorum_protocol: QuorumProtocol = QuorumProtocol.RAFT
    client_strategies: list[ClientStrategy] = Field(default_factory=list)


class CAPAnalysisResult(BaseModel):
    """Per-service CAP theorem analysis."""

    component_id: str = ""
    cap_preference: CAPPreference = CAPPreference.AP
    consistency_score: float = 0.0
    availability_score: float = 0.0
    partition_tolerance_score: float = 0.0
    tradeoff_description: str = ""
    recommendation: str = ""


class SplitBrainResult(BaseModel):
    """Split-brain detection and mitigation analysis."""

    detected: bool = False
    conflicting_components: list[str] = Field(default_factory=list)
    risk_score: float = 0.0
    recommended_mitigation: MitigationAction = MitigationAction.FENCING
    mitigation_effectiveness: float = 0.0
    estimated_data_divergence_events: int = 0
    description: str = ""


class HealingStepResult(BaseModel):
    """A single step in the healing analysis."""

    phase: HealingPhase = HealingPhase.DETECTION
    duration_seconds: float = 0.0
    description: str = ""
    requires_manual_intervention: bool = False


class HealingAnalysisResult(BaseModel):
    """Complete healing analysis after partition resolves."""

    total_healing_time_seconds: float = 0.0
    steps: list[HealingStepResult] = Field(default_factory=list)
    data_sync_required: bool = False
    estimated_sync_volume_mb: float = 0.0
    post_healing_state: str = "consistent"


class QuorumDecisionResult(BaseModel):
    """Quorum / consensus analysis result."""

    protocol: QuorumProtocol = QuorumProtocol.RAFT
    total_nodes: int = 0
    quorum_size: int = 0
    majority_partition_size: int = 0
    minority_partition_size: int = 0
    quorum_maintained: bool = True
    leader_election_needed: bool = False
    election_time_seconds: float = 0.0
    write_available: bool = True
    read_available: bool = True
    description: str = ""


class CrossAZPartitionResult(BaseModel):
    """Cross-AZ / cross-region partition impact."""

    severed_az_pairs: list[tuple[str, str]] = Field(default_factory=list)
    isolated_components: list[str] = Field(default_factory=list)
    cross_az_dependency_count: int = 0
    severed_dependency_count: int = 0
    availability_impact_percent: float = 0.0
    description: str = ""


class PartitionToleranceScore(BaseModel):
    """Partition tolerance score for a component."""

    component_id: str = ""
    score: float = 0.0
    factors: dict[str, float] = Field(default_factory=dict)
    recommendations: list[str] = Field(default_factory=list)


class NetworkSegmentResult(BaseModel):
    """Network segmentation analysis."""

    segment_id: str = ""
    component_ids: list[str] = Field(default_factory=list)
    internal_dependencies: int = 0
    external_dependencies: int = 0
    isolation_score: float = 0.0


class DivergenceModelResult(BaseModel):
    """Partition duration vs data divergence."""

    duration_seconds: float = 0.0
    estimated_divergent_writes: int = 0
    divergence_rate_per_second: float = 0.0
    reconciliation_time_seconds: float = 0.0
    data_loss_probability: float = 0.0
    risk_level: str = "low"


class LeaderElectionResult(BaseModel):
    """Leader election behavior during partition."""

    protocol: QuorumProtocol = QuorumProtocol.RAFT
    election_triggered: bool = False
    election_time_seconds: float = 0.0
    new_leader_partition: str = ""
    stale_leader_partition: str = ""
    dual_leader_risk: bool = False
    fencing_recommended: bool = False
    description: str = ""


class ClientHandlingResult(BaseModel):
    """Client-side partition handling analysis."""

    strategy: ClientStrategy = ClientStrategy.TIMEOUT
    effectiveness: float = 0.0
    estimated_failed_requests: int = 0
    estimated_retries: int = 0
    user_impact_score: float = 0.0
    recommendation: str = ""


class PartitionSimulationResult(BaseModel):
    """Top-level result of a full partition simulation."""

    timestamp: str = ""
    scenario: PartitionScenario = Field(default_factory=PartitionScenario)
    partition_sides: list[list[str]] = Field(default_factory=list)
    severed_dependencies: list[tuple[str, str]] = Field(default_factory=list)
    cap_analyses: list[CAPAnalysisResult] = Field(default_factory=list)
    split_brain: SplitBrainResult = Field(default_factory=SplitBrainResult)
    healing: HealingAnalysisResult = Field(default_factory=HealingAnalysisResult)
    quorum: QuorumDecisionResult = Field(default_factory=QuorumDecisionResult)
    cross_az: CrossAZPartitionResult = Field(default_factory=CrossAZPartitionResult)
    tolerance_scores: list[PartitionToleranceScore] = Field(default_factory=list)
    segments: list[NetworkSegmentResult] = Field(default_factory=list)
    divergence: DivergenceModelResult = Field(default_factory=DivergenceModelResult)
    leader_election: LeaderElectionResult = Field(default_factory=LeaderElectionResult)
    client_handling: list[ClientHandlingResult] = Field(default_factory=list)
    overall_risk_score: float = 0.0
    recommendations: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------


def _clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    """Clamp *value* between *lo* and *hi*."""
    return max(lo, min(hi, value))


def _now_iso() -> str:
    """Return the current UTC timestamp in ISO 8601 format."""
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class NetworkPartitionSimulator:
    """Stateless simulator for network partition scenarios.

    Provides rich, scenario-oriented analyses building on the lower-level
    ``NetworkPartitionEngine``.
    """

    # ------------------------------------------------------------------
    # Full simulation (orchestrator)
    # ------------------------------------------------------------------

    def simulate(
        self,
        graph: InfraGraph,
        scenario: PartitionScenario,
    ) -> PartitionSimulationResult:
        """Run a complete partition simulation and return the aggregate result."""
        sides = self._compute_partition_sides(graph, scenario)
        severed = self._find_severed_dependencies(graph, sides)

        cap_analyses = self.analyze_cap_per_service(graph, scenario)
        split_brain = self.detect_split_brain(graph, scenario)
        healing = self.analyze_healing(graph, scenario)
        quorum = self.analyze_quorum_decision(graph, scenario)
        cross_az = self.analyze_cross_az_partition(graph, scenario)
        tolerance_scores = self.score_partition_tolerance(graph)
        segments = self.analyze_network_segments(graph)
        divergence = self.model_divergence(graph, scenario)
        leader = self.analyze_leader_election(graph, scenario)
        client = self.analyze_client_handling(scenario)

        risk = self._compute_overall_risk(
            scenario, sides, severed, split_brain, quorum, divergence,
        )
        recs = self._build_recommendations(
            scenario, split_brain, quorum, divergence, leader, tolerance_scores,
        )

        return PartitionSimulationResult(
            timestamp=_now_iso(),
            scenario=scenario,
            partition_sides=sides,
            severed_dependencies=severed,
            cap_analyses=cap_analyses,
            split_brain=split_brain,
            healing=healing,
            quorum=quorum,
            cross_az=cross_az,
            tolerance_scores=tolerance_scores,
            segments=segments,
            divergence=divergence,
            leader_election=leader,
            client_handling=client,
            overall_risk_score=round(risk, 2),
            recommendations=recs,
        )

    # ------------------------------------------------------------------
    # CAP analysis per service
    # ------------------------------------------------------------------

    def analyze_cap_per_service(
        self,
        graph: InfraGraph,
        scenario: PartitionScenario,
    ) -> list[CAPAnalysisResult]:
        """Analyse CAP tradeoffs for each affected component."""
        results: list[CAPAnalysisResult] = []
        severity = _PARTITION_MODE_SEVERITY[scenario.mode]
        c_weight, a_weight = _CAP_WEIGHTS[scenario.cap_preference]

        for cid in scenario.affected_component_ids:
            comp = graph.get_component(cid)
            if comp is None:
                continue

            pt_score = self._component_partition_tolerance(comp)
            c_score = _clamp(100.0 * (1.0 - severity * (1.0 - c_weight)))
            a_score = _clamp(100.0 * (1.0 - severity * (1.0 - a_weight)))

            if scenario.cap_preference == CAPPreference.CP:
                tradeoff = (
                    f"{cid}: Consistency preserved at cost of availability "
                    f"(severity={severity:.2f})"
                )
                rec = (
                    f"Consider adding read replicas for {cid} to improve "
                    "read availability during partitions."
                )
            elif scenario.cap_preference == CAPPreference.AP:
                tradeoff = (
                    f"{cid}: Availability preserved at cost of consistency "
                    f"(severity={severity:.2f})"
                )
                rec = (
                    f"Implement conflict resolution (e.g. CRDTs) for {cid} "
                    "to handle stale reads."
                )
            else:
                tradeoff = (
                    f"{cid}: Balanced tradeoff between consistency and "
                    f"availability (severity={severity:.2f})"
                )
                rec = (
                    f"Tune consistency level per-query for {cid} based "
                    "on criticality."
                )

            results.append(CAPAnalysisResult(
                component_id=cid,
                cap_preference=scenario.cap_preference,
                consistency_score=round(c_score, 2),
                availability_score=round(a_score, 2),
                partition_tolerance_score=round(pt_score, 2),
                tradeoff_description=tradeoff,
                recommendation=rec,
            ))

        return results

    # ------------------------------------------------------------------
    # Split-brain detection
    # ------------------------------------------------------------------

    def detect_split_brain(
        self,
        graph: InfraGraph,
        scenario: PartitionScenario,
    ) -> SplitBrainResult:
        """Detect and assess split-brain risk."""
        sides = self._compute_partition_sides(graph, scenario)

        if len(sides) < 2:
            return SplitBrainResult(
                detected=False,
                description="No partition boundary: split-brain not possible.",
            )

        severity = _PARTITION_MODE_SEVERITY[scenario.mode]
        writable_types = {
            ComponentType.DATABASE,
            ComponentType.CACHE,
            ComponentType.STORAGE,
            ComponentType.QUEUE,
        }

        conflicting: list[str] = []
        writer_sides: list[bool] = []
        for side in sides:
            has_writer = False
            for cid in side:
                comp = graph.get_component(cid)
                if comp and comp.type in writable_types:
                    conflicting.append(cid)
                    has_writer = True
            writer_sides.append(has_writer)

        multi_writer = sum(1 for w in writer_sides if w) > 1

        if not multi_writer:
            return SplitBrainResult(
                detected=False,
                conflicting_components=conflicting,
                risk_score=0.0,
                description="Writable components are on one side only.",
            )

        risk = _clamp(severity * 100.0 * (len(conflicting) / max(len(graph.components), 1)))
        divergent = max(1, int(scenario.duration_seconds / 10 * severity * len(conflicting)))

        mitigation = self._select_mitigation(scenario)
        effectiveness = _MITIGATION_EFFECTIVENESS[mitigation]

        return SplitBrainResult(
            detected=True,
            conflicting_components=conflicting,
            risk_score=round(risk, 2),
            recommended_mitigation=mitigation,
            mitigation_effectiveness=effectiveness,
            estimated_data_divergence_events=divergent,
            description=(
                f"Split-brain detected: {len(conflicting)} writable components "
                f"across {len(sides)} partition sides."
            ),
        )

    # ------------------------------------------------------------------
    # Healing analysis
    # ------------------------------------------------------------------

    def analyze_healing(
        self,
        graph: InfraGraph,
        scenario: PartitionScenario,
    ) -> HealingAnalysisResult:
        """Analyse how the system recovers after partition resolves."""
        severity = _PARTITION_MODE_SEVERITY[scenario.mode]
        steps: list[HealingStepResult] = []
        total_time = 0.0

        # Determine which phases are needed
        phases_needed: list[HealingPhase] = [
            HealingPhase.DETECTION,
            HealingPhase.RECONNECTION,
        ]

        needs_sync = severity >= 0.5 or scenario.duration_seconds > 60
        needs_conflict = (
            scenario.mode in (PartitionMode.FULL, PartitionMode.ASYMMETRIC)
            and severity >= 0.5
        )
        needs_election = scenario.quorum_protocol != QuorumProtocol.NONE and severity >= 0.5

        if needs_sync:
            phases_needed.append(HealingPhase.STATE_SYNC)
        if needs_conflict:
            phases_needed.append(HealingPhase.CONFLICT_RESOLUTION)
        if needs_election:
            phases_needed.append(HealingPhase.LEADER_ELECTION)

        phases_needed.append(HealingPhase.VERIFICATION)
        phases_needed.append(HealingPhase.COMPLETED)

        duration_factor = 1.0 + scenario.duration_seconds / 300.0

        for phase in phases_needed:
            base = _HEALING_PHASE_DURATION_SECONDS[phase]
            dur = base * duration_factor * (1.0 + severity * 0.5)
            manual = phase == HealingPhase.CONFLICT_RESOLUTION and severity > 0.75
            desc = self._healing_phase_description(phase, dur, manual)
            steps.append(HealingStepResult(
                phase=phase,
                duration_seconds=round(dur, 2),
                description=desc,
                requires_manual_intervention=manual,
            ))
            total_time += dur

        sync_volume = 0.0
        if needs_sync:
            affected_count = len(scenario.affected_component_ids)
            sync_volume = affected_count * scenario.duration_seconds * severity * 0.1

        post_state = "consistent"
        if needs_conflict and severity > 0.75:
            post_state = "requires_manual_review"
        elif needs_conflict:
            post_state = "auto_resolved"
        elif needs_sync:
            post_state = "eventually_consistent"

        return HealingAnalysisResult(
            total_healing_time_seconds=round(total_time, 2),
            steps=steps,
            data_sync_required=needs_sync,
            estimated_sync_volume_mb=round(sync_volume, 2),
            post_healing_state=post_state,
        )

    # ------------------------------------------------------------------
    # Quorum / consensus analysis
    # ------------------------------------------------------------------

    def analyze_quorum_decision(
        self,
        graph: InfraGraph,
        scenario: PartitionScenario,
    ) -> QuorumDecisionResult:
        """Analyse quorum-based decision making during partition."""
        sides = self._compute_partition_sides(graph, scenario)
        total_nodes = sum(len(s) for s in sides)

        if total_nodes == 0:
            return QuorumDecisionResult(
                protocol=scenario.quorum_protocol,
                description="No nodes in partition scope.",
            )

        quorum_size = total_nodes // 2 + 1
        majority_side = max(sides, key=len) if sides else []
        minority_count = total_nodes - len(majority_side)

        quorum_ok = len(majority_side) >= quorum_size

        severity = _PARTITION_MODE_SEVERITY[scenario.mode]
        needs_election = (
            scenario.quorum_protocol != QuorumProtocol.NONE
            and severity >= 0.5
            and scenario.mode in (PartitionMode.FULL, PartitionMode.ASYMMETRIC)
        )

        election_time = 0.0
        if needs_election:
            base = _QUORUM_ELECTION_BASE_SECONDS[scenario.quorum_protocol]
            election_time = base * (1.0 + severity)

        write_ok = quorum_ok
        read_ok = quorum_ok or scenario.cap_preference == CAPPreference.AP

        parts: list[str] = []
        parts.append("Quorum maintained" if quorum_ok else "Quorum lost")
        parts.append(f"majority={len(majority_side)}, minority={minority_count}")
        if needs_election:
            parts.append(f"election ~{election_time:.0f}s ({scenario.quorum_protocol.value})")

        return QuorumDecisionResult(
            protocol=scenario.quorum_protocol,
            total_nodes=total_nodes,
            quorum_size=quorum_size,
            majority_partition_size=len(majority_side),
            minority_partition_size=minority_count,
            quorum_maintained=quorum_ok,
            leader_election_needed=needs_election,
            election_time_seconds=round(election_time, 2),
            write_available=write_ok,
            read_available=read_ok,
            description="; ".join(parts),
        )

    # ------------------------------------------------------------------
    # Cross-AZ partition
    # ------------------------------------------------------------------

    def analyze_cross_az_partition(
        self,
        graph: InfraGraph,
        scenario: PartitionScenario,
    ) -> CrossAZPartitionResult:
        """Model cross-AZ or cross-region partition impact."""
        sides = self._compute_partition_sides(graph, scenario)
        if len(sides) < 2:
            return CrossAZPartitionResult(description="Single partition side; no cross-AZ impact.")

        side_sets = [set(s) for s in sides]

        # Determine AZ of each component
        az_map: dict[str, str] = {}
        for comp in graph.components.values():
            az = comp.region.availability_zone or comp.region.region or "default"
            az_map[comp.id] = az

        # Find AZ pairs that are severed
        severed_az: set[tuple[str, str]] = set()
        isolated: list[str] = []

        edges = graph.all_dependency_edges()
        cross_az_count = 0
        severed_count = 0

        for edge in edges:
            src_az = az_map.get(edge.source_id, "default")
            tgt_az = az_map.get(edge.target_id, "default")
            if src_az != tgt_az:
                cross_az_count += 1

            for i, si in enumerate(side_sets):
                for j, sj in enumerate(side_sets):
                    if i >= j:
                        continue
                    if (edge.source_id in si and edge.target_id in sj) or (
                        edge.source_id in sj and edge.target_id in si
                    ):
                        severed_count += 1
                        if src_az != tgt_az:
                            pair = tuple(sorted((src_az, tgt_az)))
                            severed_az.add(pair)  # type: ignore[arg-type]

        # Find truly isolated components (all their deps are severed)
        affected_set = set(scenario.affected_component_ids)
        for cid in affected_set:
            comp = graph.get_component(cid)
            if comp is None:
                continue
            deps_out = graph.get_dependencies(cid)
            deps_in = graph.get_dependents(cid)
            all_deps = [d.id for d in deps_out] + [d.id for d in deps_in]
            if all_deps and all(d not in affected_set for d in all_deps):
                isolated.append(cid)

        total_edges = len(edges)
        avail_impact = 0.0
        if total_edges > 0:
            avail_impact = (severed_count / total_edges) * 100.0

        severity = _PARTITION_MODE_SEVERITY[scenario.mode]
        avail_impact *= severity

        return CrossAZPartitionResult(
            severed_az_pairs=sorted(severed_az),  # type: ignore[arg-type]
            isolated_components=sorted(isolated),
            cross_az_dependency_count=cross_az_count,
            severed_dependency_count=severed_count,
            availability_impact_percent=round(_clamp(avail_impact), 2),
            description=(
                f"{severed_count} dependencies severed across "
                f"{len(severed_az)} AZ pairs."
            ),
        )

    # ------------------------------------------------------------------
    # Partition tolerance scoring
    # ------------------------------------------------------------------

    def score_partition_tolerance(
        self,
        graph: InfraGraph,
    ) -> list[PartitionToleranceScore]:
        """Score each component's partition tolerance (0-100)."""
        results: list[PartitionToleranceScore] = []

        for comp in graph.components.values():
            factors: dict[str, float] = {}
            recs: list[str] = []
            score = 50.0  # baseline

            # Replicas
            replica_bonus = min(25.0, (comp.replicas - 1) * 12.5)
            factors["replicas"] = replica_bonus
            score += replica_bonus
            if comp.replicas < 2:
                recs.append(f"Add replicas for {comp.id} (currently {comp.replicas}).")

            # Failover
            if comp.failover.enabled:
                factors["failover"] = 15.0
                score += 15.0
            else:
                factors["failover"] = 0.0
                recs.append(f"Enable failover for {comp.id}.")

            # Autoscaling
            if comp.autoscaling.enabled:
                factors["autoscaling"] = 5.0
                score += 5.0
            else:
                factors["autoscaling"] = 0.0

            # Circuit breakers on incoming edges
            dependents = graph.get_dependents(comp.id)
            if dependents:
                cb_count = 0
                for dep_comp in dependents:
                    edge = graph.get_dependency_edge(dep_comp.id, comp.id)
                    if edge and edge.circuit_breaker.enabled:
                        cb_count += 1
                cb_ratio = cb_count / len(dependents)
                cb_bonus = cb_ratio * 10.0
                factors["circuit_breakers"] = round(cb_bonus, 2)
                score += cb_bonus
                if cb_ratio < 1.0:
                    recs.append(
                        f"Enable circuit breakers on all edges targeting {comp.id}."
                    )
            else:
                factors["circuit_breakers"] = 0.0

            # Network segmentation (cross-region penalty)
            if comp.region.region:
                factors["region_configured"] = 5.0
                score += 5.0
            else:
                factors["region_configured"] = 0.0

            score = _clamp(score)
            results.append(PartitionToleranceScore(
                component_id=comp.id,
                score=round(score, 2),
                factors=factors,
                recommendations=recs,
            ))

        results.sort(key=lambda s: s.score)
        return results

    # ------------------------------------------------------------------
    # Network segmentation
    # ------------------------------------------------------------------

    def analyze_network_segments(
        self,
        graph: InfraGraph,
    ) -> list[NetworkSegmentResult]:
        """Analyse network segments based on AZ / region grouping."""
        seg_map: dict[str, list[str]] = {}

        for comp in graph.components.values():
            seg_id = comp.region.availability_zone or comp.region.region or "default"
            seg_map.setdefault(seg_id, []).append(comp.id)

        results: list[NetworkSegmentResult] = []
        edges = graph.all_dependency_edges()

        for seg_id, comp_ids in sorted(seg_map.items()):
            cid_set = set(comp_ids)
            internal = 0
            external = 0
            for edge in edges:
                src_in = edge.source_id in cid_set
                tgt_in = edge.target_id in cid_set
                if src_in and tgt_in:
                    internal += 1
                elif src_in or tgt_in:
                    external += 1

            total = internal + external
            iso_score = (internal / total * 100.0) if total > 0 else 100.0

            results.append(NetworkSegmentResult(
                segment_id=seg_id,
                component_ids=sorted(comp_ids),
                internal_dependencies=internal,
                external_dependencies=external,
                isolation_score=round(iso_score, 2),
            ))

        return results

    # ------------------------------------------------------------------
    # Divergence modeling
    # ------------------------------------------------------------------

    def model_divergence(
        self,
        graph: InfraGraph,
        scenario: PartitionScenario,
    ) -> DivergenceModelResult:
        """Model partition duration vs data divergence."""
        severity = _PARTITION_MODE_SEVERITY[scenario.mode]
        writable_types = {
            ComponentType.DATABASE,
            ComponentType.CACHE,
            ComponentType.STORAGE,
            ComponentType.QUEUE,
        }

        writer_count = 0
        for cid in scenario.affected_component_ids:
            comp = graph.get_component(cid)
            if comp and comp.type in writable_types:
                writer_count += 1

        if writer_count == 0:
            return DivergenceModelResult(
                duration_seconds=scenario.duration_seconds,
                risk_level="low",
            )

        # Divergence rate: writes per second per writable component
        rate = writer_count * severity * 0.5
        total_writes = int(scenario.duration_seconds * rate)

        # Reconciliation: ~2 seconds per divergent write
        reconciliation = total_writes * 2.0

        # Data loss probability increases with duration and severity
        loss_prob = _clamp(
            1.0 - math.exp(-severity * scenario.duration_seconds / 600.0),
            0.0,
            1.0,
        )

        if loss_prob >= 0.5:
            risk = "critical"
        elif loss_prob >= 0.2:
            risk = "high"
        elif loss_prob >= 0.05:
            risk = "medium"
        else:
            risk = "low"

        return DivergenceModelResult(
            duration_seconds=scenario.duration_seconds,
            estimated_divergent_writes=total_writes,
            divergence_rate_per_second=round(rate, 4),
            reconciliation_time_seconds=round(reconciliation, 2),
            data_loss_probability=round(loss_prob, 4),
            risk_level=risk,
        )

    # ------------------------------------------------------------------
    # Leader election
    # ------------------------------------------------------------------

    def analyze_leader_election(
        self,
        graph: InfraGraph,
        scenario: PartitionScenario,
    ) -> LeaderElectionResult:
        """Analyse leader election behavior during partition."""
        if scenario.quorum_protocol == QuorumProtocol.NONE:
            return LeaderElectionResult(
                protocol=QuorumProtocol.NONE,
                election_triggered=False,
                description="No consensus protocol configured.",
            )

        sides = self._compute_partition_sides(graph, scenario)
        severity = _PARTITION_MODE_SEVERITY[scenario.mode]

        triggered = severity > 0.5 and len(sides) >= 2
        if not triggered:
            return LeaderElectionResult(
                protocol=scenario.quorum_protocol,
                election_triggered=False,
                description="Partition severity too low to trigger election.",
            )

        base_time = _QUORUM_ELECTION_BASE_SECONDS[scenario.quorum_protocol]
        election_time = base_time * (1.0 + severity)

        majority_side = max(sides, key=len) if sides else []
        minority_sides = [s for s in sides if s is not majority_side]

        # Dual leader risk when partition is asymmetric
        dual_risk = (
            scenario.mode == PartitionMode.ASYMMETRIC
            and len(minority_sides) > 0
            and len(minority_sides[0]) > 0
        )

        total = sum(len(s) for s in sides)
        quorum = total // 2 + 1
        fencing = dual_risk or len(majority_side) < quorum

        new_leader_part = "majority"
        stale_leader_part = "minority" if len(sides) >= 2 else ""

        desc_parts = [
            f"{scenario.quorum_protocol.value} election triggered",
            f"election time ~{election_time:.1f}s",
        ]
        if dual_risk:
            desc_parts.append("DUAL LEADER RISK")
        if fencing:
            desc_parts.append("fencing recommended")

        return LeaderElectionResult(
            protocol=scenario.quorum_protocol,
            election_triggered=True,
            election_time_seconds=round(election_time, 2),
            new_leader_partition=new_leader_part,
            stale_leader_partition=stale_leader_part,
            dual_leader_risk=dual_risk,
            fencing_recommended=fencing,
            description="; ".join(desc_parts),
        )

    # ------------------------------------------------------------------
    # Client-side handling
    # ------------------------------------------------------------------

    def analyze_client_handling(
        self,
        scenario: PartitionScenario,
    ) -> list[ClientHandlingResult]:
        """Analyse client-side strategies for partition handling."""
        results: list[ClientHandlingResult] = []
        severity = _PARTITION_MODE_SEVERITY[scenario.mode]

        strategies = scenario.client_strategies or [
            ClientStrategy.TIMEOUT,
            ClientStrategy.RETRY,
            ClientStrategy.CIRCUIT_BREAK,
        ]

        for strat in strategies:
            effectiveness = _CLIENT_STRATEGY_EFFECTIVENESS[strat]
            failed_reqs = max(0, int(100 * severity * (1.0 - effectiveness)))
            retries = int(failed_reqs * 0.5) if strat == ClientStrategy.RETRY else 0
            user_impact = _clamp(severity * (1.0 - effectiveness) * 100.0)
            rec = self._client_strategy_recommendation(strat, severity)

            results.append(ClientHandlingResult(
                strategy=strat,
                effectiveness=effectiveness,
                estimated_failed_requests=failed_reqs,
                estimated_retries=retries,
                user_impact_score=round(user_impact, 2),
                recommendation=rec,
            ))

        return results

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_partition_sides(
        graph: InfraGraph,
        scenario: PartitionScenario,
    ) -> list[list[str]]:
        """Split components into partition sides."""
        affected = set(scenario.affected_component_ids)
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
    def _find_severed_dependencies(
        graph: InfraGraph,
        sides: list[list[str]],
    ) -> list[tuple[str, str]]:
        """Identify dependency edges crossing the partition."""
        if len(sides) < 2:
            return []

        side_sets = [set(s) for s in sides]
        severed: list[tuple[str, str]] = []
        for edge in graph.all_dependency_edges():
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
    def _component_partition_tolerance(comp: Component) -> float:
        """Quick partition tolerance estimate for a single component."""
        score = 30.0
        if comp.replicas >= 3:
            score += 30.0
        elif comp.replicas >= 2:
            score += 15.0
        if comp.failover.enabled:
            score += 20.0
        if comp.autoscaling.enabled:
            score += 10.0
        if comp.region.region:
            score += 10.0
        return _clamp(score)

    @staticmethod
    def _select_mitigation(scenario: PartitionScenario) -> MitigationAction:
        """Choose the best mitigation action for split-brain."""
        if scenario.quorum_protocol != QuorumProtocol.NONE:
            return MitigationAction.QUORUM_LEADER
        if scenario.mode == PartitionMode.FULL:
            return MitigationAction.FENCING
        if scenario.mode == PartitionMode.ASYMMETRIC:
            return MitigationAction.AUTOMATIC_ROLLBACK
        return MitigationAction.CRDT_MERGE

    @staticmethod
    def _healing_phase_description(
        phase: HealingPhase,
        duration: float,
        manual: bool,
    ) -> str:
        """Build a human-readable description for a healing step."""
        descs: dict[HealingPhase, str] = {
            HealingPhase.DETECTION: "Detect that the partition has healed",
            HealingPhase.RECONNECTION: "Re-establish network connectivity",
            HealingPhase.STATE_SYNC: "Synchronize diverged state across partitions",
            HealingPhase.CONFLICT_RESOLUTION: "Resolve conflicting writes",
            HealingPhase.LEADER_ELECTION: "Re-elect cluster leader",
            HealingPhase.VERIFICATION: "Verify cluster consistency",
            HealingPhase.COMPLETED: "Healing completed; normal operations resumed",
        }
        base = descs.get(phase, str(phase.value))
        if manual:
            base += " (MANUAL INTERVENTION REQUIRED)"
        return f"{base} (~{duration:.0f}s)"

    @staticmethod
    def _client_strategy_recommendation(
        strat: ClientStrategy,
        severity: float,
    ) -> str:
        """Generate a recommendation for a client strategy."""
        recs: dict[ClientStrategy, str] = {
            ClientStrategy.TIMEOUT: (
                "Set aggressive read timeouts and surface errors early."
            ),
            ClientStrategy.RETRY: (
                "Use exponential backoff with jitter; cap retries at 3."
            ),
            ClientStrategy.CIRCUIT_BREAK: (
                "Configure circuit breaker with half-open probes "
                "to detect partition healing."
            ),
            ClientStrategy.FAILOVER: (
                "Route traffic to secondary region/endpoint on failure."
            ),
            ClientStrategy.HEDGE: (
                "Send parallel requests to multiple backends; "
                "use first successful response."
            ),
        }
        base = recs.get(strat, "Review client error handling.")
        if severity >= 0.75:
            base += " High severity: combine with failover strategy."
        return base

    @staticmethod
    def _compute_overall_risk(
        scenario: PartitionScenario,
        sides: list[list[str]],
        severed: list[tuple[str, str]],
        split_brain: SplitBrainResult,
        quorum: QuorumDecisionResult,
        divergence: DivergenceModelResult,
    ) -> float:
        """Compute an overall risk score (0-100)."""
        severity = _PARTITION_MODE_SEVERITY[scenario.mode]
        risk = severity * 30.0

        if split_brain.detected:
            risk += split_brain.risk_score * 0.3

        if not quorum.quorum_maintained:
            risk += 20.0

        risk += divergence.data_loss_probability * 20.0

        if len(severed) > 0:
            risk += min(10.0, len(severed) * 2.0)

        return _clamp(risk)

    @staticmethod
    def _build_recommendations(
        scenario: PartitionScenario,
        split_brain: SplitBrainResult,
        quorum: QuorumDecisionResult,
        divergence: DivergenceModelResult,
        leader: LeaderElectionResult,
        tolerance_scores: list[PartitionToleranceScore],
    ) -> list[str]:
        """Build a prioritised list of recommendations."""
        recs: list[str] = []

        if split_brain.detected:
            recs.append(
                f"Split-brain detected: implement {split_brain.recommended_mitigation.value} "
                f"(effectiveness={split_brain.mitigation_effectiveness:.0%})."
            )

        if not quorum.quorum_maintained:
            recs.append(
                "Quorum lost during partition. Increase replica count to "
                "maintain majority."
            )

        if leader.dual_leader_risk:
            recs.append(
                "Dual leader risk detected. Enable fencing tokens to prevent "
                "stale leader writes."
            )

        if divergence.risk_level in ("high", "critical"):
            recs.append(
                f"Data divergence risk is {divergence.risk_level}. "
                "Reduce partition duration exposure or implement CRDTs."
            )

        # Recommend improvements for low-scoring components
        for ts in tolerance_scores:
            if ts.score < 60.0:
                for r in ts.recommendations:
                    if r not in recs:
                        recs.append(r)

        if not recs:
            recs.append("No critical issues detected for this partition scenario.")

        return recs
