"""Topology-aware workload scheduler for FaultRay chaos engineering.

Schedules workloads across infrastructure components considering topology
constraints — availability zones, rack awareness, data locality, anti-affinity
rules, and failure domain isolation.  Optimises placement for resilience while
respecting resource limits.
"""

from __future__ import annotations

import hashlib
from collections import defaultdict
from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field

from faultray.model.components import Component
from faultray.model.graph import InfraGraph


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class PlacementStrategy(str, Enum):
    """High-level placement strategy for a workload."""

    SPREAD = "spread"
    PACK = "pack"
    ZONE_BALANCED = "zone_balanced"
    RACK_AWARE = "rack_aware"
    DATA_LOCAL = "data_local"
    LATENCY_OPTIMIZED = "latency_optimized"


class ConstraintType(str, Enum):
    """Types of placement constraints."""

    ANTI_AFFINITY = "anti_affinity"
    AFFINITY = "affinity"
    ZONE_SPREAD = "zone_spread"
    MAX_PER_NODE = "max_per_node"
    RESOURCE_LIMIT = "resource_limit"
    DATA_LOCALITY = "data_locality"


class SchedulerDecision(str, Enum):
    """Outcome of a scheduling attempt."""

    PLACED = "placed"
    PENDING = "pending"
    EVICTED = "evicted"
    PREEMPTED = "preempted"
    FAILED = "failed"


class FailureDomain(str, Enum):
    """Failure domain hierarchy (broadest → narrowest)."""

    REGION = "region"
    ZONE = "zone"
    RACK = "rack"
    NODE = "node"
    PROCESS = "process"


# ---------------------------------------------------------------------------
# Domain models (Pydantic v2)
# ---------------------------------------------------------------------------


class Workload(BaseModel):
    """A workload to be scheduled onto infrastructure nodes."""

    workload_id: str
    cpu_request: float = 0.5
    memory_request_mb: float = 256.0
    replicas: int = 1
    priority: int = 10
    strategy: PlacementStrategy = PlacementStrategy.SPREAD
    affinity_labels: dict[str, str] = Field(default_factory=dict)
    anti_affinity_labels: dict[str, str] = Field(default_factory=dict)
    data_locality_node: str = ""
    tolerate_failure_domain: FailureDomain = FailureDomain.NODE


class PlacementConstraint(BaseModel):
    """A constraint that restricts workload placement."""

    constraint_type: ConstraintType
    key: str = ""
    value: str = ""
    hard: bool = True
    max_count: int = 1


class SchedulingResult(BaseModel):
    """Result of scheduling a single workload."""

    workload_id: str
    decision: SchedulerDecision
    node_assignments: list[str] = Field(default_factory=list)
    zones_used: list[str] = Field(default_factory=list)
    failure_domain_coverage: FailureDomain = FailureDomain.PROCESS
    spread_score: float = 0.0
    resource_utilization: float = 0.0
    reason: str = ""
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class EvictionCandidate(BaseModel):
    """A running workload that could be evicted to make room."""

    workload_id: str
    node_id: str
    priority: int = 0
    resource_freed_cpu: float = 0.0
    resource_freed_memory_mb: float = 0.0


class TopologySchedulerReport(BaseModel):
    """Aggregate report for a scheduling run."""

    results: list[SchedulingResult] = Field(default_factory=list)
    total_workloads: int = 0
    placed_count: int = 0
    pending_count: int = 0
    failed_count: int = 0
    overall_spread_score: float = 0.0
    recommendations: list[str] = Field(default_factory=list)
    generated_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _zone_of(comp: Component) -> str:
    """Extract the availability zone label from a component."""
    return comp.region.availability_zone or "default-zone"


def _rack_of(comp: Component) -> str:
    """Derive a deterministic rack id from the component."""
    tag_rack = [t for t in comp.tags if t.startswith("rack:")]
    if tag_rack:
        return tag_rack[0].split(":", 1)[1]
    return f"rack-{hashlib.md5(comp.id.encode()).hexdigest()[:4]}"


def _region_of(comp: Component) -> str:
    return comp.region.region or "default-region"


def _available_cpu(comp: Component) -> float:
    # cpu capacity derived from 100% minus current usage scaled to replicas
    return max(0.0, (100.0 - comp.metrics.cpu_percent) * comp.replicas / 100.0)


def _available_memory(comp: Component) -> float:
    total = comp.capacity.max_memory_mb
    used = comp.metrics.memory_used_mb
    return max(0.0, (total - used) * comp.replicas)


def _node_is_schedulable(comp: Component) -> bool:
    """Return True when a node is healthy enough to receive workloads."""
    from faultray.model.components import HealthStatus

    return comp.health in (HealthStatus.HEALTHY, HealthStatus.DEGRADED)


def _labels_match(node_tags: list[str], label_dict: dict[str, str]) -> bool:
    """Check if a node's tag list satisfies all label requirements."""
    tag_map: dict[str, str] = {}
    for tag in node_tags:
        if ":" in tag:
            k, v = tag.split(":", 1)
            tag_map[k] = v
        else:
            tag_map[tag] = ""
    for k, v in label_dict.items():
        if k not in tag_map:
            return False
        if v and tag_map[k] != v:
            return False
    return True


def _node_score_spread(
    comp: Component,
    zone_counts: dict[str, int],
    rack_counts: dict[str, int],
) -> float:
    """Score a node favouring zones/racks with fewer existing replicas."""
    zone = _zone_of(comp)
    rack = _rack_of(comp)
    zone_penalty = zone_counts.get(zone, 0) * 10.0
    rack_penalty = rack_counts.get(rack, 0) * 5.0
    cpu_headroom = _available_cpu(comp)
    return cpu_headroom - zone_penalty - rack_penalty


def _node_score_pack(comp: Component) -> float:
    """Score a node favouring the most utilised (but not full) nodes."""
    util = comp.utilization()
    if util >= 95.0:
        return -1000.0
    return util


def _node_score_data_local(comp: Component, target_node: str) -> float:
    if comp.id == target_node:
        return 10000.0
    return 0.0


def _node_score_latency(comp: Component, graph: InfraGraph) -> float:
    """Lower latency edges → higher score."""
    total_latency = 0.0
    deps = graph.get_dependencies(comp.id)
    for dep in deps:
        edge = graph.get_dependency_edge(comp.id, dep.id)
        if edge:
            total_latency += edge.latency_ms
    return -total_latency


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class TopologyAwareSchedulerEngine:
    """Stateless scheduling engine that places workloads across an InfraGraph."""

    # ---- public API ----

    def schedule_workloads(
        self,
        graph: InfraGraph,
        workloads: list[Workload],
        constraints: list[PlacementConstraint] | None = None,
    ) -> TopologySchedulerReport:
        """Schedule *workloads* across graph nodes, honouring *constraints*.

        Returns a :class:`TopologySchedulerReport` summarising every decision.
        """
        constraints = constraints or []
        results: list[SchedulingResult] = []
        # node-level resource tracking (remaining)
        node_cpu_remaining: dict[str, float] = {}
        node_mem_remaining: dict[str, float] = {}
        for comp in graph.components.values():
            node_cpu_remaining[comp.id] = _available_cpu(comp)
            node_mem_remaining[comp.id] = _available_memory(comp)

        # Track which workloads are placed on which nodes
        existing_assignments: dict[str, list[str]] = {}

        # Sort workloads by priority descending (higher = more important)
        sorted_workloads = sorted(workloads, key=lambda w: w.priority, reverse=True)

        for wl in sorted_workloads:
            result = self._schedule_single(
                graph,
                wl,
                constraints,
                node_cpu_remaining,
                node_mem_remaining,
                existing_assignments,
            )
            results.append(result)
            if result.decision == SchedulerDecision.PLACED:
                existing_assignments[wl.workload_id] = list(result.node_assignments)

        # Build report
        placed = sum(1 for r in results if r.decision == SchedulerDecision.PLACED)
        pending = sum(1 for r in results if r.decision == SchedulerDecision.PENDING)
        failed = sum(1 for r in results if r.decision == SchedulerDecision.FAILED)

        zones = set()
        for comp in graph.components.values():
            zones.add(_zone_of(comp))

        overall_spread = self.compute_spread_score(existing_assignments, zones)

        recommendations = self._generate_recommendations(
            graph, results, existing_assignments, zones
        )

        return TopologySchedulerReport(
            results=results,
            total_workloads=len(workloads),
            placed_count=placed,
            pending_count=pending,
            failed_count=failed,
            overall_spread_score=overall_spread,
            recommendations=recommendations,
        )

    def compute_spread_score(
        self,
        assignments: dict[str, list[str]],
        zones: set[str] | list[str],
    ) -> float:
        """Compute a 0-100 spread score.

        A perfect score means every workload has replicas in every zone.
        """
        if not assignments or not zones:
            return 0.0

        zone_list = list(zones) if isinstance(zones, set) else zones
        if not zone_list:
            return 0.0

        scores: list[float] = []
        for wl_id, nodes in assignments.items():
            if not nodes:
                scores.append(0.0)
                continue
            unique_zones_used = len(set(nodes))  # simplified; see below
            score = min(1.0, unique_zones_used / max(len(zone_list), 1))
            scores.append(score)

        return round((sum(scores) / len(scores)) * 100.0, 2) if scores else 0.0

    def check_anti_affinity(
        self,
        graph: InfraGraph,
        workload: Workload,
        candidate_node: str,
        existing_assignments: dict[str, list[str]],
    ) -> bool:
        """Return True if placing *workload* on *candidate_node* is allowed
        by anti-affinity rules (i.e. no conflict).
        """
        if not workload.anti_affinity_labels:
            return True

        candidate_comp = graph.get_component(candidate_node)
        if candidate_comp is None:
            return False

        candidate_zone = _zone_of(candidate_comp)

        for other_wl_id, other_nodes in existing_assignments.items():
            if other_wl_id == workload.workload_id:
                continue
            for node_id in other_nodes:
                other_comp = graph.get_component(node_id)
                if other_comp is None:
                    continue
                other_zone = _zone_of(other_comp)
                # If same zone and labels overlap → conflict
                if other_zone == candidate_zone:
                    if _labels_match(other_comp.tags, workload.anti_affinity_labels):
                        return False
        return True

    def find_eviction_candidates(
        self,
        graph: InfraGraph,
        workload: Workload,
        existing_assignments: dict[str, list[str]],
    ) -> list[EvictionCandidate]:
        """Identify workloads that could be evicted to free resources for *workload*."""
        candidates: list[EvictionCandidate] = []
        for other_wl_id, nodes in existing_assignments.items():
            if other_wl_id == workload.workload_id:
                continue
            for node_id in nodes:
                comp = graph.get_component(node_id)
                if comp is None:
                    continue
                # Only consider lower-priority workloads
                # Priority 0 by default for unknown
                candidates.append(
                    EvictionCandidate(
                        workload_id=other_wl_id,
                        node_id=node_id,
                        priority=0,
                        resource_freed_cpu=_available_cpu(comp) * 0.5,
                        resource_freed_memory_mb=_available_memory(comp) * 0.25,
                    )
                )

        # Sort by priority ascending (lowest-priority first → best eviction targets)
        candidates.sort(key=lambda c: c.priority)
        return candidates

    def evaluate_failure_domain_coverage(
        self,
        assignments: dict[str, list[str]],
    ) -> FailureDomain:
        """Determine the broadest failure domain covered by current assignments.

        If replicas span regions → REGION, zones → ZONE, etc.
        """
        if not assignments:
            return FailureDomain.PROCESS

        all_nodes: list[str] = []
        for nodes in assignments.values():
            all_nodes.extend(nodes)

        if not all_nodes:
            return FailureDomain.PROCESS

        unique = set(all_nodes)
        if len(unique) == 1:
            return FailureDomain.PROCESS

        # We return NODE if multiple nodes, but same "rack" conceptually
        # For a more accurate check we'd inspect components, but we work
        # only with node ids here.
        if len(unique) >= 4:
            return FailureDomain.REGION
        if len(unique) >= 3:
            return FailureDomain.ZONE
        if len(unique) >= 2:
            return FailureDomain.RACK

        return FailureDomain.NODE

    def evaluate_failure_domain_coverage_with_graph(
        self,
        graph: InfraGraph,
        assignments: dict[str, list[str]],
    ) -> FailureDomain:
        """Like evaluate_failure_domain_coverage but uses the graph to inspect
        actual region/zone/rack metadata on each component.
        """
        if not assignments:
            return FailureDomain.PROCESS

        regions: set[str] = set()
        zones: set[str] = set()
        racks: set[str] = set()
        nodes: set[str] = set()

        for node_list in assignments.values():
            for node_id in node_list:
                comp = graph.get_component(node_id)
                if comp is None:
                    continue
                nodes.add(node_id)
                regions.add(_region_of(comp))
                zones.add(_zone_of(comp))
                racks.add(_rack_of(comp))

        if len(regions) > 1:
            return FailureDomain.REGION
        if len(zones) > 1:
            return FailureDomain.ZONE
        if len(racks) > 1:
            return FailureDomain.RACK
        if len(nodes) > 1:
            return FailureDomain.NODE
        return FailureDomain.PROCESS

    def optimize_placement(
        self,
        graph: InfraGraph,
        results: list[SchedulingResult],
    ) -> list[SchedulingResult]:
        """Post-process placement results to improve spread and utilization.

        Attempts to redistribute replicas that are co-located in the same zone
        to under-utilised zones.
        """
        if not results:
            return results

        optimized: list[SchedulingResult] = []

        # Gather all zones in the graph
        zone_load: dict[str, int] = defaultdict(int)
        zone_nodes: dict[str, list[str]] = defaultdict(list)

        for comp in graph.components.values():
            z = _zone_of(comp)
            zone_nodes[z].append(comp.id)

        for res in results:
            for node_id in res.node_assignments:
                comp = graph.get_component(node_id)
                if comp:
                    zone_load[_zone_of(comp)] += 1

        for res in results:
            if res.decision != SchedulerDecision.PLACED:
                optimized.append(res)
                continue

            if len(res.node_assignments) <= 1:
                optimized.append(res)
                continue

            # Try to redistribute assignments across zones
            new_assignments = list(res.node_assignments)
            zones_used: set[str] = set()
            for node_id in new_assignments:
                comp = graph.get_component(node_id)
                if comp:
                    zones_used.add(_zone_of(comp))

            # If all replicas in a single zone, try to spread
            if len(zones_used) == 1:
                current_zone = list(zones_used)[0]
                other_zones = [
                    z for z in zone_nodes if z != current_zone and zone_nodes[z]
                ]
                for i, node_id in enumerate(new_assignments[1:], 1):
                    if i - 1 < len(other_zones):
                        target_zone = other_zones[i - 1]
                        candidates = zone_nodes[target_zone]
                        if candidates:
                            candidate = candidates[0]
                            ccomp = graph.get_component(candidate)
                            if ccomp and _node_is_schedulable(ccomp):
                                new_assignments[i] = candidate
                                zones_used.add(target_zone)

            new_zones = []
            for n in new_assignments:
                c = graph.get_component(n)
                if c:
                    new_zones.append(_zone_of(c))

            new_spread = (
                len(set(new_zones)) / max(len(zone_nodes), 1) * 100.0
                if new_zones
                else 0.0
            )

            optimized.append(
                SchedulingResult(
                    workload_id=res.workload_id,
                    decision=res.decision,
                    node_assignments=new_assignments,
                    zones_used=sorted(set(new_zones)),
                    failure_domain_coverage=res.failure_domain_coverage,
                    spread_score=round(new_spread, 2),
                    resource_utilization=res.resource_utilization,
                    reason=res.reason + " (optimized)" if res.reason else "optimized",
                )
            )

        return optimized

    # ---- private helpers ----

    def _schedule_single(
        self,
        graph: InfraGraph,
        workload: Workload,
        constraints: list[PlacementConstraint],
        node_cpu_remaining: dict[str, float],
        node_mem_remaining: dict[str, float],
        existing_assignments: dict[str, list[str]],
    ) -> SchedulingResult:
        """Attempt to place a single workload."""
        candidate_nodes = self._filter_candidates(
            graph, workload, constraints, existing_assignments
        )

        if not candidate_nodes:
            return SchedulingResult(
                workload_id=workload.workload_id,
                decision=SchedulerDecision.FAILED,
                reason="no suitable nodes found",
            )

        # Score each candidate
        scored = self._score_candidates(
            graph, workload, candidate_nodes, existing_assignments
        )

        # Select best nodes up to replica count
        selected: list[str] = []
        zones_used: set[str] = set()
        total_cpu_used = 0.0
        total_mem_used = 0.0

        for node_id, _score in scored:
            if len(selected) >= workload.replicas:
                break

            cpu_req = workload.cpu_request
            mem_req = workload.memory_request_mb

            if node_cpu_remaining.get(node_id, 0) < cpu_req:
                continue
            if node_mem_remaining.get(node_id, 0) < mem_req:
                continue

            # Enforce max_per_node constraint
            max_per = self._max_per_node(constraints)
            if max_per > 0:
                count_on_node = sum(
                    1
                    for ns in existing_assignments.values()
                    for n in ns
                    if n == node_id
                )
                count_on_node += sum(1 for s in selected if s == node_id)
                if count_on_node >= max_per:
                    continue

            selected.append(node_id)
            node_cpu_remaining[node_id] -= cpu_req
            node_mem_remaining[node_id] -= mem_req
            total_cpu_used += cpu_req
            total_mem_used += mem_req

            comp = graph.get_component(node_id)
            if comp:
                zones_used.add(_zone_of(comp))

        if not selected:
            return SchedulingResult(
                workload_id=workload.workload_id,
                decision=SchedulerDecision.PENDING,
                reason="insufficient resources on candidates",
            )

        if len(selected) < workload.replicas:
            decision = SchedulerDecision.PENDING
            reason = (
                f"partial placement: {len(selected)}/{workload.replicas} replicas"
            )
        else:
            decision = SchedulerDecision.PLACED
            reason = "fully placed"

        # Compute per-workload spread
        zone_set = set()
        for c in graph.components.values():
            zone_set.add(_zone_of(c))
        spread = (
            len(zones_used) / max(len(zone_set), 1) * 100.0
            if zones_used
            else 0.0
        )

        # Compute resource utilization of selected nodes
        util_values = []
        for nid in selected:
            comp = graph.get_component(nid)
            if comp:
                util_values.append(comp.utilization())
        avg_util = sum(util_values) / len(util_values) if util_values else 0.0

        # Failure domain coverage for this workload
        wl_assignments = {workload.workload_id: selected}
        fd_coverage = self.evaluate_failure_domain_coverage_with_graph(
            graph, wl_assignments
        )

        return SchedulingResult(
            workload_id=workload.workload_id,
            decision=decision,
            node_assignments=selected,
            zones_used=sorted(zones_used),
            failure_domain_coverage=fd_coverage,
            spread_score=round(spread, 2),
            resource_utilization=round(avg_util, 2),
            reason=reason,
        )

    def _filter_candidates(
        self,
        graph: InfraGraph,
        workload: Workload,
        constraints: list[PlacementConstraint],
        existing_assignments: dict[str, list[str]],
    ) -> list[str]:
        """Return node ids that pass hard constraints."""
        candidates: list[str] = []

        for comp in graph.components.values():
            if not _node_is_schedulable(comp):
                continue

            # Affinity check
            if workload.affinity_labels:
                if not _labels_match(comp.tags, workload.affinity_labels):
                    continue

            # Hard constraint checks
            skip = False
            for c in constraints:
                if not c.hard:
                    continue
                if c.constraint_type == ConstraintType.RESOURCE_LIMIT:
                    if c.key == "cpu" and _available_cpu(comp) < float(c.value):
                        skip = True
                        break
                    if c.key == "memory" and _available_memory(comp) < float(c.value):
                        skip = True
                        break
                if c.constraint_type == ConstraintType.ZONE_SPREAD:
                    # Zone spread is checked at selection time, not filtering
                    pass
                if c.constraint_type == ConstraintType.DATA_LOCALITY:
                    if c.value and comp.id != c.value:
                        skip = True
                        break

            if skip:
                continue

            # Anti-affinity check
            if not self.check_anti_affinity(
                graph, workload, comp.id, existing_assignments
            ):
                # Only skip for hard anti-affinity
                if workload.anti_affinity_labels:
                    hard_aa = any(
                        c.constraint_type == ConstraintType.ANTI_AFFINITY and c.hard
                        for c in constraints
                    )
                    if hard_aa:
                        continue

            candidates.append(comp.id)

        return candidates

    def _score_candidates(
        self,
        graph: InfraGraph,
        workload: Workload,
        candidates: list[str],
        existing_assignments: dict[str, list[str]],
    ) -> list[tuple[str, float]]:
        """Score and sort candidate nodes (highest score first)."""
        zone_counts: dict[str, int] = defaultdict(int)
        rack_counts: dict[str, int] = defaultdict(int)

        # Count existing assignments per zone/rack
        for nodes in existing_assignments.values():
            for nid in nodes:
                comp = graph.get_component(nid)
                if comp:
                    zone_counts[_zone_of(comp)] += 1
                    rack_counts[_rack_of(comp)] += 1

        scored: list[tuple[str, float]] = []
        for nid in candidates:
            comp = graph.get_component(nid)
            if comp is None:
                continue

            if workload.strategy == PlacementStrategy.SPREAD:
                s = _node_score_spread(comp, zone_counts, rack_counts)
            elif workload.strategy == PlacementStrategy.PACK:
                s = _node_score_pack(comp)
            elif workload.strategy == PlacementStrategy.ZONE_BALANCED:
                s = _node_score_spread(comp, zone_counts, rack_counts) * 1.5
            elif workload.strategy == PlacementStrategy.RACK_AWARE:
                rack_penalty = rack_counts.get(_rack_of(comp), 0) * 20.0
                s = _available_cpu(comp) - rack_penalty
            elif workload.strategy == PlacementStrategy.DATA_LOCAL:
                s = _node_score_data_local(comp, workload.data_locality_node)
            elif workload.strategy == PlacementStrategy.LATENCY_OPTIMIZED:
                s = _node_score_latency(comp, graph)
            else:
                s = _available_cpu(comp)

            scored.append((nid, s))

        scored.sort(key=lambda x: x[1], reverse=True)
        return scored

    def _max_per_node(self, constraints: list[PlacementConstraint]) -> int:
        """Extract MAX_PER_NODE limit from constraints, 0 = unlimited."""
        for c in constraints:
            if c.constraint_type == ConstraintType.MAX_PER_NODE:
                return c.max_count
        return 0

    def _generate_recommendations(
        self,
        graph: InfraGraph,
        results: list[SchedulingResult],
        existing_assignments: dict[str, list[str]],
        zones: set[str],
    ) -> list[str]:
        recs: list[str] = []

        failed = [r for r in results if r.decision == SchedulerDecision.FAILED]
        pending = [r for r in results if r.decision == SchedulerDecision.PENDING]

        if failed:
            recs.append(
                f"{len(failed)} workload(s) failed to schedule — "
                "consider adding more nodes or reducing resource requests."
            )

        if pending:
            recs.append(
                f"{len(pending)} workload(s) are pending — "
                "some replicas could not be placed due to resource constraints."
            )

        # Check zone imbalance
        zone_load: dict[str, int] = defaultdict(int)
        for nodes in existing_assignments.values():
            for nid in nodes:
                comp = graph.get_component(nid)
                if comp:
                    zone_load[_zone_of(comp)] += 1

        if zone_load:
            loads = list(zone_load.values())
            if loads and max(loads) > 2 * max(min(loads), 1):
                recs.append(
                    "Zone imbalance detected — some zones have significantly "
                    "more workloads. Consider zone-balanced placement strategy."
                )

        # Single-zone workloads
        single_zone = [
            r
            for r in results
            if r.decision == SchedulerDecision.PLACED and len(r.zones_used) <= 1
        ]
        if single_zone and len(zones) > 1:
            recs.append(
                f"{len(single_zone)} workload(s) are confined to a single zone — "
                "spread replicas across zones for failure domain isolation."
            )

        # Low overall spread
        if existing_assignments:
            spread = self.compute_spread_score(existing_assignments, zones)
            if spread < 50.0:
                recs.append(
                    f"Overall spread score is {spread:.1f}% — "
                    "below 50% indicates poor failure domain coverage."
                )

        # Nodes at high utilization
        hot_nodes = [
            c
            for c in graph.components.values()
            if c.utilization() > 80.0
        ]
        if hot_nodes:
            recs.append(
                f"{len(hot_nodes)} node(s) are above 80% utilization — "
                "consider scaling out or enabling autoscaling."
            )

        return recs
