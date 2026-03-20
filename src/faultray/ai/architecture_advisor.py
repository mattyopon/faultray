# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Business Source License 1.1. See LICENSE file for details.

"""AI Architecture Advisor - Intelligent infrastructure redesign recommendations.

Analyzes current infrastructure topology and generates concrete, actionable
architecture redesign proposals to achieve specific resilience targets.

Unlike simple recommendations ("add more replicas"), this advisor generates
complete architecture blueprints with:
- Specific component changes (add, modify, remove)
- New dependency configurations
- Cost-benefit analysis for each change
- Priority ordering (quick wins -> major refactors)
- Before/after resilience score comparison
- Architecture pattern recommendations (active-active, CQRS, circuit breaker, bulkhead, etc.)
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from enum import Enum

from faultray.model.components import (
    AutoScalingConfig,
    CircuitBreakerConfig,
    Component,
    ComponentType,
    Dependency,
    FailoverConfig,
)
from faultray.model.graph import InfraGraph

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class ArchitecturePattern(str, Enum):
    """Well-known resilience architecture patterns."""

    ACTIVE_ACTIVE = "active_active"
    ACTIVE_PASSIVE = "active_passive"
    CIRCUIT_BREAKER = "circuit_breaker"
    BULKHEAD = "bulkhead"
    RETRY_WITH_BACKOFF = "retry_with_backoff"
    CQRS = "cqrs"
    EVENT_SOURCING = "event_sourcing"
    SAGA = "saga"
    SIDECAR = "sidecar"
    STRANGLER_FIG = "strangler_fig"
    CELL_BASED = "cell_based"
    MULTI_REGION = "multi_region"
    READ_REPLICA = "read_replica"
    WRITE_AHEAD_LOG = "write_ahead_log"
    CACHE_ASIDE = "cache_aside"
    RATE_LIMITING = "rate_limiting"


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class ArchitectureChange:
    """A single proposed change to the infrastructure architecture."""

    change_type: str  # add_component, modify_component, remove_component, add_dependency, modify_dependency, add_pattern
    component_id: str | None
    description: str
    before_state: dict | None
    after_state: dict
    pattern: ArchitecturePattern | None = None
    estimated_cost: str = "$0"  # "$0", "$100-500/mo", "$500-2000/mo", "$2000+/mo"
    effort: str = "hours"  # "minutes", "hours", "days", "weeks", "months"
    resilience_impact: float = 0.0  # estimated score improvement
    risk_reduction: str = ""  # what risk it mitigates


@dataclass
class ArchitectureProposal:
    """A complete architecture redesign proposal."""

    name: str  # e.g., "High Availability Upgrade"
    description: str
    target_nines: float
    changes: list[ArchitectureChange] = field(default_factory=list)
    current_score: float = 0.0
    projected_score: float = 0.0
    estimated_monthly_cost: str = "$0"
    total_effort: str = "hours"
    patterns_applied: list[ArchitecturePattern] = field(default_factory=list)
    trade_offs: list[str] = field(default_factory=list)
    prerequisites: list[str] = field(default_factory=list)


@dataclass
class ArchitectureReport:
    """Complete architecture advisory report."""

    current_assessment: str = ""
    current_score: float = 0.0
    current_nines: float = 0.0
    target_nines: float = 4.0
    gap_analysis: str = ""
    proposals: list[ArchitectureProposal] = field(default_factory=list)
    quick_wins: list[ArchitectureChange] = field(default_factory=list)
    critical_changes: list[ArchitectureChange] = field(default_factory=list)
    architecture_patterns_recommended: list[tuple[ArchitecturePattern, str]] = field(
        default_factory=list
    )
    anti_patterns_detected: list[tuple[str, str]] = field(default_factory=list)
    mermaid_diagram: str = ""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _score_to_nines(score: float) -> float:
    """Convert a resilience score (0-100) to approximate availability nines.

    Mapping:
        100 -> ~5.0 nines (99.999%)
        90  -> ~3.0 nines (99.9%)
        80  -> ~2.5 nines
        60  -> ~2.0 nines (99%)
        0   -> ~0.0 nines
    """
    if score <= 0:
        return 0.0
    if score >= 100:
        return 5.0
    # Logarithmic mapping: nines = -log10(1 - score/100)
    try:
        nines = -math.log10(1.0 - score / 100.0)
    except (ValueError, ZeroDivisionError):
        nines = 5.0
    return round(min(nines, 5.0), 2)


def _nines_to_score(nines: float) -> float:
    """Convert availability nines to approximate resilience score (0-100)."""
    if nines <= 0:
        return 0.0
    if nines >= 5:
        return 100.0
    return round((1.0 - 10 ** (-nines)) * 100.0, 1)


def _estimate_total_cost(changes: list[ArchitectureChange]) -> str:
    """Estimate total monthly cost from a list of changes."""
    cost_order = {"$0": 0, "$100-500/mo": 300, "$500-2000/mo": 1250, "$2000+/mo": 3000}
    total = sum(cost_order.get(c.estimated_cost, 0) for c in changes)
    if total == 0:
        return "$0"
    if total < 500:
        return "$100-500/mo"
    if total < 2000:
        return "$500-2000/mo"
    return "$2000+/mo"


def _estimate_total_effort(changes: list[ArchitectureChange]) -> str:
    """Estimate total effort from a list of changes."""
    effort_order = {"minutes": 0, "hours": 1, "days": 2, "weeks": 3, "months": 4}
    if not changes:
        return "minutes"
    max_effort = max(effort_order.get(c.effort, 0) for c in changes)
    for label, value in effort_order.items():
        if value == max_effort:
            return label
    return "hours"


# ---------------------------------------------------------------------------
# Architecture Advisor Engine
# ---------------------------------------------------------------------------


class ArchitectureAdvisor:
    """Analyzes infrastructure and recommends architecture redesigns.

    Produces actionable proposals to achieve specific resilience targets,
    including quick wins, anti-pattern detection, pattern recommendations,
    and visual Mermaid architecture diagrams.
    """

    def advise(
        self, graph: InfraGraph, target_nines: float = 4.0
    ) -> ArchitectureReport:
        """Generate a full architecture advisory report.

        Args:
            graph: Current infrastructure graph.
            target_nines: Target availability in nines (e.g. 4.0 = 99.99%).

        Returns:
            ArchitectureReport with proposals, quick wins, anti-patterns, etc.
        """
        current_score = graph.resilience_score()
        current_nines = _score_to_nines(current_score)
        target_score = _nines_to_score(target_nines)

        # Detect issues
        quick_wins = self.generate_quick_wins(graph)
        anti_patterns = self.detect_anti_patterns(graph)
        patterns = self.recommend_patterns(graph)
        critical_changes = self._detect_critical_changes(graph, target_nines)

        # Build proposals (ordered by effort: quick wins first)
        proposals = self._build_proposals(
            graph, current_score, target_nines, quick_wins, critical_changes, patterns
        )

        # Generate mermaid diagram from the first (best) proposal
        all_changes = []
        if proposals:
            all_changes = proposals[0].changes
        mermaid = self.generate_mermaid_diagram(graph, all_changes)

        # Current assessment
        assessment = self._generate_assessment(
            graph, current_score, current_nines, target_nines
        )
        gap = self._generate_gap_analysis(
            current_score, current_nines, target_score, target_nines
        )

        return ArchitectureReport(
            current_assessment=assessment,
            current_score=round(current_score, 1),
            current_nines=current_nines,
            target_nines=target_nines,
            gap_analysis=gap,
            proposals=proposals,
            quick_wins=quick_wins,
            critical_changes=critical_changes,
            architecture_patterns_recommended=patterns,
            anti_patterns_detected=anti_patterns,
            mermaid_diagram=mermaid,
        )

    # ------------------------------------------------------------------
    # Quick wins
    # ------------------------------------------------------------------

    def generate_quick_wins(self, graph: InfraGraph) -> list[ArchitectureChange]:
        """Detect quick-win improvements that boost resilience with minimal effort."""
        wins: list[ArchitectureChange] = []

        for comp in graph.components.values():
            dependents = graph.get_dependents(comp.id)

            # SPOF: replicas=1 with dependents
            if comp.replicas <= 1 and len(dependents) > 0:
                wins.append(
                    ArchitectureChange(
                        change_type="modify_component",
                        component_id=comp.id,
                        description=f"Add replica to '{comp.id}' (currently single instance with {len(dependents)} dependent(s))",
                        before_state={"replicas": comp.replicas},
                        after_state={"replicas": max(2, comp.replicas + 1)},
                        pattern=ArchitecturePattern.ACTIVE_PASSIVE,
                        estimated_cost="$100-500/mo",
                        effort="hours",
                        resilience_impact=min(15.0, len(dependents) * 5.0),
                        risk_reduction=f"Eliminates SPOF for {comp.id}",
                    )
                )

            # No failover
            if not comp.failover.enabled and len(dependents) > 0:
                wins.append(
                    ArchitectureChange(
                        change_type="modify_component",
                        component_id=comp.id,
                        description=f"Enable failover for '{comp.id}'",
                        before_state={"failover_enabled": False},
                        after_state={
                            "failover_enabled": True,
                            "promotion_time_seconds": 30.0,
                        },
                        pattern=ArchitecturePattern.ACTIVE_PASSIVE,
                        estimated_cost="$0",
                        effort="hours",
                        resilience_impact=5.0,
                        risk_reduction=f"Automatic recovery for {comp.id} failures",
                    )
                )

            # No autoscaling
            if not comp.autoscaling.enabled:
                wins.append(
                    ArchitectureChange(
                        change_type="modify_component",
                        component_id=comp.id,
                        description=f"Enable autoscaling for '{comp.id}'",
                        before_state={"autoscaling_enabled": False},
                        after_state={
                            "autoscaling_enabled": True,
                            "min_replicas": comp.replicas,
                            "max_replicas": max(comp.replicas * 3, 6),
                        },
                        estimated_cost="$100-500/mo",
                        effort="hours",
                        resilience_impact=3.0,
                        risk_reduction=f"Handles load spikes on {comp.id}",
                    )
                )

            # No health checks (no failover implies no health check)
            if not comp.failover.enabled and comp.replicas >= 2:
                wins.append(
                    ArchitectureChange(
                        change_type="modify_component",
                        component_id=comp.id,
                        description=f"Add health check to '{comp.id}'",
                        before_state={"health_check": False},
                        after_state={
                            "health_check_interval_seconds": 10.0,
                            "failover_threshold": 3,
                        },
                        estimated_cost="$0",
                        effort="minutes",
                        resilience_impact=2.0,
                        risk_reduction=f"Detect failures in {comp.id} faster",
                    )
                )

        # Missing circuit breakers on dependency edges
        for edge in graph.all_dependency_edges():
            if not edge.circuit_breaker.enabled:
                graph.get_component(edge.target_id)
                wins.append(
                    ArchitectureChange(
                        change_type="modify_dependency",
                        component_id=f"{edge.source_id}->{edge.target_id}",
                        description=f"Enable circuit breaker on {edge.source_id} -> {edge.target_id}",
                        before_state={"circuit_breaker_enabled": False},
                        after_state={
                            "circuit_breaker_enabled": True,
                            "failure_threshold": 5,
                            "recovery_timeout_seconds": 60.0,
                        },
                        pattern=ArchitecturePattern.CIRCUIT_BREAKER,
                        estimated_cost="$0",
                        effort="minutes",
                        resilience_impact=3.0,
                        risk_reduction=f"Prevents cascade failure through {edge.source_id} -> {edge.target_id}",
                    )
                )

        # Check if cache layer is missing but DB has dependents
        db_comps = [
            c for c in graph.components.values() if c.type == ComponentType.DATABASE
        ]
        cache_comps = [
            c for c in graph.components.values() if c.type == ComponentType.CACHE
        ]
        if db_comps and not cache_comps:
            wins.append(
                ArchitectureChange(
                    change_type="add_component",
                    component_id="cache-layer",
                    description="Add caching layer (Redis/Memcached) to reduce database load",
                    before_state=None,
                    after_state={
                        "type": "cache",
                        "replicas": 2,
                        "id": "cache-layer",
                    },
                    pattern=ArchitecturePattern.CACHE_ASIDE,
                    estimated_cost="$100-500/mo",
                    effort="days",
                    resilience_impact=5.0,
                    risk_reduction="Reduces database load and adds read redundancy",
                )
            )

        # Sort by impact descending, effort ascending
        effort_order = {"minutes": 0, "hours": 1, "days": 2, "weeks": 3, "months": 4}
        wins.sort(
            key=lambda w: (-w.resilience_impact, effort_order.get(w.effort, 5))
        )

        return wins

    # ------------------------------------------------------------------
    # Anti-pattern detection
    # ------------------------------------------------------------------

    def detect_anti_patterns(self, graph: InfraGraph) -> list[tuple[str, str]]:
        """Detect common infrastructure anti-patterns in the graph."""
        anti_patterns: list[tuple[str, str]] = []

        # God Component: single component with >5 dependents
        for comp in graph.components.values():
            dependents = graph.get_dependents(comp.id)
            if len(dependents) > 5:
                anti_patterns.append((
                    "God Component",
                    f"Component '{comp.id}' has {len(dependents)} dependents. "
                    "A single failure would cascade to most of the system. "
                    "Consider decomposing into smaller services.",
                ))

        # Chain of Death: dependency chain depth > 4
        critical_paths = graph.get_critical_paths()
        for path in critical_paths:
            if len(path) > 4:
                chain_str = " -> ".join(path)
                anti_patterns.append((
                    "Chain of Death",
                    f"Deep dependency chain ({len(path)} hops): {chain_str}. "
                    "Long chains amplify failure probability. "
                    "Consider flattening or adding circuit breakers.",
                ))
                break  # Only report the worst one

        # Shared Everything: all components depend on same single DB
        db_dependents: dict[str, int] = {}
        for comp in graph.components.values():
            if comp.type == ComponentType.DATABASE:
                deps = graph.get_dependents(comp.id)
                db_dependents[comp.id] = len(deps)

        total_non_db = sum(
            1
            for c in graph.components.values()
            if c.type != ComponentType.DATABASE
        )
        for db_id, dep_count in db_dependents.items():
            if dep_count > 0 and total_non_db > 0 and dep_count >= total_non_db * 0.8:
                anti_patterns.append((
                    "Shared Everything",
                    f"Database '{db_id}' is a dependency for {dep_count} of {total_non_db} "
                    "non-database components. A single DB failure affects the entire system. "
                    "Consider read replicas, CQRS, or service-level databases.",
                ))

        # No Bulkhead: no isolation between failure domains
        regions = set()
        azs = set()
        for comp in graph.components.values():
            if comp.region.region:
                regions.add(comp.region.region)
            if comp.region.availability_zone:
                azs.add(comp.region.availability_zone)

        if len(graph.components) > 2 and len(regions) <= 1 and len(azs) <= 1:
            anti_patterns.append((
                "No Bulkhead",
                "All components appear to be in the same failure domain "
                "(no region or availability zone diversity). "
                "Consider distributing across availability zones or regions.",
            ))

        # Missing Circuit Breaker: external API calls without circuit breaker
        for edge in graph.all_dependency_edges():
            target = graph.get_component(edge.target_id)
            if target and target.type == ComponentType.EXTERNAL_API:
                if not edge.circuit_breaker.enabled:
                    anti_patterns.append((
                        "Missing Circuit Breaker",
                        f"External API dependency {edge.source_id} -> {edge.target_id} "
                        "lacks a circuit breaker. External services can fail unpredictably "
                        "and cause cascading failures.",
                    ))

        # Single Region: all components in one availability zone
        if len(graph.components) > 3 and len(regions) == 1:
            anti_patterns.append((
                "Single Region",
                f"All {len(graph.components)} components are in region "
                f"'{next(iter(regions))}'. A regional outage would cause "
                "complete service failure. Consider multi-region deployment.",
            ))

        # Overloaded Gateway: single load balancer with many dependents
        for comp in graph.components.values():
            if comp.type == ComponentType.LOAD_BALANCER:
                deps = graph.get_dependents(comp.id)
                if comp.replicas <= 1 and len(deps) > 0:
                    anti_patterns.append((
                        "Overloaded Gateway",
                        f"Load balancer '{comp.id}' is a single entry point "
                        f"with {comp.replicas} replica(s). Consider adding "
                        "redundancy or splitting traffic across multiple LBs.",
                    ))

        # Synchronous Everything: all dependencies are synchronous (no queues)
        has_queue = any(
            c.type == ComponentType.QUEUE for c in graph.components.values()
        )
        has_async = any(
            e.dependency_type == "async" for e in graph.all_dependency_edges()
        )
        if (
            len(graph.components) > 3
            and not has_queue
            and not has_async
            and graph.all_dependency_edges()
        ):
            anti_patterns.append((
                "Synchronous Everything",
                "No message queues or async dependencies detected. "
                "All communication appears synchronous, creating tight coupling. "
                "Consider adding message queues for non-critical paths.",
            ))

        return anti_patterns

    # ------------------------------------------------------------------
    # Pattern recommendations
    # ------------------------------------------------------------------

    def recommend_patterns(
        self, graph: InfraGraph
    ) -> list[tuple[ArchitecturePattern, str]]:
        """Recommend architecture patterns based on detected issues."""
        recommendations: list[tuple[ArchitecturePattern, str]] = []
        seen_patterns: set[ArchitecturePattern] = set()

        def _add(pattern: ArchitecturePattern, reason: str) -> None:
            if pattern not in seen_patterns:
                seen_patterns.add(pattern)
                recommendations.append((pattern, reason))

        # SPOF detected -> ACTIVE_ACTIVE or ACTIVE_PASSIVE
        for comp in graph.components.values():
            dependents = graph.get_dependents(comp.id)
            if comp.replicas <= 1 and len(dependents) > 0:
                if len(dependents) >= 3:
                    _add(
                        ArchitecturePattern.ACTIVE_ACTIVE,
                        f"Component '{comp.id}' is a critical SPOF with {len(dependents)} dependents. "
                        "Active-active provides zero-downtime failover.",
                    )
                else:
                    _add(
                        ArchitecturePattern.ACTIVE_PASSIVE,
                        f"Component '{comp.id}' is a SPOF. Active-passive adds "
                        "standby capacity for automatic failover.",
                    )
                break  # Only recommend once

        # Deep dependency chains -> CIRCUIT_BREAKER + BULKHEAD
        critical_paths = graph.get_critical_paths()
        if critical_paths and len(critical_paths[0]) > 4:
            _add(
                ArchitecturePattern.CIRCUIT_BREAKER,
                f"Dependency chain depth of {len(critical_paths[0])} detected. "
                "Circuit breakers prevent cascade failures through deep chains.",
            )
            _add(
                ArchitecturePattern.BULKHEAD,
                "Bulkhead isolation prevents failures in one chain from "
                "affecting independent service paths.",
            )

        # High DB load -> READ_REPLICA + CACHE_ASIDE + CQRS
        db_comps = [
            c for c in graph.components.values() if c.type == ComponentType.DATABASE
        ]
        for db in db_comps:
            deps = graph.get_dependents(db.id)
            if len(deps) >= 2:
                _add(
                    ArchitecturePattern.READ_REPLICA,
                    f"Database '{db.id}' serves {len(deps)} consumers. "
                    "Read replicas distribute read load.",
                )
                _add(
                    ArchitecturePattern.CACHE_ASIDE,
                    "Cache-aside pattern reduces direct database reads "
                    "and provides faster response times.",
                )
                if len(deps) >= 4:
                    _add(
                        ArchitecturePattern.CQRS,
                        "CQRS separates read and write models, allowing "
                        "independent scaling of read-heavy workloads.",
                    )
                break

        # No async processing -> EVENT_SOURCING
        has_queue = any(
            c.type == ComponentType.QUEUE for c in graph.components.values()
        )
        if not has_queue and len(graph.components) > 3:
            _add(
                ArchitecturePattern.EVENT_SOURCING,
                "No message queues detected. Event sourcing decouples "
                "producers from consumers and enables async processing.",
            )

        # External API dependency -> CIRCUIT_BREAKER + RETRY_WITH_BACKOFF
        for edge in graph.all_dependency_edges():
            target = graph.get_component(edge.target_id)
            if target and target.type == ComponentType.EXTERNAL_API:
                _add(
                    ArchitecturePattern.CIRCUIT_BREAKER,
                    f"External API dependency '{target.id}' requires circuit "
                    "breaker protection against third-party outages.",
                )
                _add(
                    ArchitecturePattern.RETRY_WITH_BACKOFF,
                    f"Retry with exponential backoff for transient failures "
                    f"on external API '{target.id}'.",
                )
                break

        # Monolithic structure (many components, all interconnected)
        n = len(graph.components)
        e = len(graph.all_dependency_edges())
        if n >= 5 and e >= n * 1.5:
            _add(
                ArchitecturePattern.STRANGLER_FIG,
                "Dense dependency graph suggests tightly coupled architecture. "
                "Strangler fig pattern enables gradual migration to microservices.",
            )
            _add(
                ArchitecturePattern.CELL_BASED,
                "Cell-based architecture isolates failures to individual cells, "
                "limiting blast radius of any single failure.",
            )

        # Multi-region if single region detected
        regions = {
            c.region.region for c in graph.components.values() if c.region.region
        }
        if len(regions) <= 1 and len(graph.components) > 3:
            _add(
                ArchitecturePattern.MULTI_REGION,
                "Single-region deployment detected. Multi-region architecture "
                "provides resilience against regional outages.",
            )

        # Rate limiting if load balancer present without rate limiting
        for comp in graph.components.values():
            if comp.type == ComponentType.LOAD_BALANCER:
                if not comp.security.rate_limiting:
                    _add(
                        ArchitecturePattern.RATE_LIMITING,
                        f"Load balancer '{comp.id}' lacks rate limiting. "
                        "Rate limiting protects against traffic spikes and DDoS.",
                    )
                    break

        return recommendations

    # ------------------------------------------------------------------
    # Mermaid diagram generation
    # ------------------------------------------------------------------

    def generate_mermaid_diagram(
        self, graph: InfraGraph, changes: list[ArchitectureChange]
    ) -> str:
        """Generate a Mermaid.js diagram showing proposed architecture.

        Color-coded nodes:
        - green = existing unchanged
        - blue = modified
        - orange = new
        """
        lines: list[str] = ["graph TB"]

        # Track which components are modified or new
        modified_ids: set[str] = set()
        new_ids: set[str] = set()
        for change in changes:
            if change.change_type == "add_component" and change.component_id:
                new_ids.add(change.component_id)
            elif change.change_type == "modify_component" and change.component_id:
                modified_ids.add(change.component_id)
            elif change.change_type == "modify_dependency" and change.component_id:
                # component_id is "source->target"
                parts = change.component_id.split("->")
                for p in parts:
                    if p in graph.components:
                        modified_ids.add(p)

        # Group components by availability zone / region
        az_groups: dict[str, list[Component]] = {}
        for comp in graph.components.values():
            az = comp.region.availability_zone or comp.region.region or "default"
            az_groups.setdefault(az, []).append(comp)

        # Render subgraphs
        for az_name, comps in az_groups.items():
            if az_name != "default":
                safe_name = az_name.replace("-", "_").replace(" ", "_")
                lines.append(f'    subgraph {safe_name}["{az_name}"]')
            for comp in comps:
                node_label = self._mermaid_node_label(comp)
                css_class = "existing"
                if comp.id in modified_ids:
                    css_class = "modified"
                elif comp.id in new_ids:
                    css_class = "new"
                indent = "        " if az_name != "default" else "    "
                lines.append(f"{indent}{comp.id}{node_label}:::{css_class}")
            if az_name != "default":
                lines.append("    end")

        # Add new components from changes
        for change in changes:
            if change.change_type == "add_component" and change.component_id:
                if change.component_id not in graph.components:
                    comp_type = change.after_state.get("type", "custom")
                    replicas = change.after_state.get("replicas", 1)
                    label = f"{change.component_id}"
                    if replicas > 1:
                        label += f" x{replicas}"
                    shape = self._mermaid_shape_for_type(comp_type)
                    lines.append(
                        f"    {change.component_id}{shape[0]}{label}{shape[1]}:::new"
                    )

        # Render edges
        for edge in graph.all_dependency_edges():
            arrow = "-->"
            if edge.dependency_type == "optional":
                arrow = "-.->|optional|"
            elif edge.dependency_type == "async":
                arrow = "-.->|async|"
            elif edge.circuit_breaker.enabled:
                arrow = "-->|CB|"

            # Check if this edge is for a replication relationship
            if edge.dependency_type == "requires" and not edge.circuit_breaker.enabled:
                arrow = " --> "

            lines.append(f"    {edge.source_id}{arrow}{edge.target_id}")

        # Add new dependency edges from changes
        for change in changes:
            if change.change_type == "add_dependency" and change.component_id:
                parts = change.component_id.split("->")
                if len(parts) == 2:
                    lines.append(
                        f"    {parts[0]} -.->|new| {parts[1]}"
                    )

        # Class definitions
        lines.append("    classDef existing fill:#28a745,color:#fff")
        lines.append("    classDef modified fill:#007bff,color:#fff")
        lines.append("    classDef new fill:#fd7e14,color:#fff")

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Apply proposal
    # ------------------------------------------------------------------

    def apply_proposal(
        self, graph: InfraGraph, proposal: ArchitectureProposal
    ) -> InfraGraph:
        """Apply a proposal to a graph, returning a modified copy.

        This creates a deep copy of the graph and applies each change in the
        proposal to produce the resulting infrastructure.
        """
        new_graph = InfraGraph()

        # Deep copy existing components
        for comp in graph.components.values():
            new_comp = comp.model_copy(deep=True)
            new_graph.add_component(new_comp)

        # Deep copy existing dependencies
        for edge in graph.all_dependency_edges():
            new_edge = edge.model_copy(deep=True)
            new_graph.add_dependency(new_edge)

        # Apply changes
        for change in proposal.changes:
            self._apply_change(new_graph, change)

        return new_graph

    # ------------------------------------------------------------------
    # Compare before/after
    # ------------------------------------------------------------------

    def compare_before_after(
        self, original: InfraGraph, modified: InfraGraph
    ) -> dict:
        """Compare resilience metrics between original and modified graphs."""
        orig_score = original.resilience_score()
        mod_score = modified.resilience_score()
        orig_v2 = original.resilience_score_v2()
        mod_v2 = modified.resilience_score_v2()

        return {
            "original_score": round(orig_score, 1),
            "modified_score": round(mod_score, 1),
            "score_improvement": round(mod_score - orig_score, 1),
            "original_nines": _score_to_nines(orig_score),
            "modified_nines": _score_to_nines(mod_score),
            "nines_improvement": round(
                _score_to_nines(mod_score) - _score_to_nines(orig_score), 2
            ),
            "original_breakdown": orig_v2.get("breakdown", {}),
            "modified_breakdown": mod_v2.get("breakdown", {}),
            "original_components": len(original.components),
            "modified_components": len(modified.components),
            "original_dependencies": len(original.all_dependency_edges()),
            "modified_dependencies": len(modified.all_dependency_edges()),
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _detect_critical_changes(
        self, graph: InfraGraph, target_nines: float
    ) -> list[ArchitectureChange]:
        """Detect changes that are absolutely necessary to reach the target."""
        critical: list[ArchitectureChange] = []
        current_score = graph.resilience_score()
        target_score = _nines_to_score(target_nines)

        if current_score >= target_score:
            return critical

        # Critical SPOFs that block reaching the target
        for comp in graph.components.values():
            dependents = graph.get_dependents(comp.id)
            if comp.replicas <= 1 and len(dependents) >= 2:
                critical.append(
                    ArchitectureChange(
                        change_type="modify_component",
                        component_id=comp.id,
                        description=f"CRITICAL: '{comp.id}' must have replicas >= 2 to reach {target_nines} nines",
                        before_state={"replicas": comp.replicas},
                        after_state={
                            "replicas": 3,
                            "failover_enabled": True,
                        },
                        pattern=ArchitecturePattern.ACTIVE_ACTIVE,
                        estimated_cost="$500-2000/mo",
                        effort="days",
                        resilience_impact=15.0,
                        risk_reduction=f"Eliminates critical SPOF in {comp.id}",
                    )
                )

        # If target >= 4 nines, require circuit breakers on all 'requires' edges
        if target_nines >= 4.0:
            for edge in graph.all_dependency_edges():
                if (
                    edge.dependency_type == "requires"
                    and not edge.circuit_breaker.enabled
                ):
                    critical.append(
                        ArchitectureChange(
                            change_type="modify_dependency",
                            component_id=f"{edge.source_id}->{edge.target_id}",
                            description=f"CRITICAL: Circuit breaker required on {edge.source_id} -> {edge.target_id}",
                            before_state={"circuit_breaker_enabled": False},
                            after_state={
                                "circuit_breaker_enabled": True,
                                "failure_threshold": 5,
                                "recovery_timeout_seconds": 30.0,
                            },
                            pattern=ArchitecturePattern.CIRCUIT_BREAKER,
                            estimated_cost="$0",
                            effort="hours",
                            resilience_impact=5.0,
                            risk_reduction=f"Prevent cascade failure through {edge.source_id} -> {edge.target_id}",
                        )
                    )

        return critical

    def _build_proposals(
        self,
        graph: InfraGraph,
        current_score: float,
        target_nines: float,
        quick_wins: list[ArchitectureChange],
        critical_changes: list[ArchitectureChange],
        patterns: list[tuple[ArchitecturePattern, str]],
    ) -> list[ArchitectureProposal]:
        """Build tiered proposals from quick wins to full redesign."""
        proposals: list[ArchitectureProposal] = []
        _nines_to_score(target_nines)

        # Proposal 1: Quick Wins Only
        if quick_wins:
            qw_impact = sum(c.resilience_impact for c in quick_wins[:5])
            projected = min(100.0, current_score + qw_impact)
            qw_changes = quick_wins[:5]
            qw_patterns = list(
                {c.pattern for c in qw_changes if c.pattern is not None}
            )
            proposals.append(
                ArchitectureProposal(
                    name="Quick Wins",
                    description="Low-effort changes that immediately improve resilience. "
                    "These can be implemented with minimal risk and downtime.",
                    target_nines=target_nines,
                    changes=qw_changes,
                    current_score=round(current_score, 1),
                    projected_score=round(projected, 1),
                    estimated_monthly_cost=_estimate_total_cost(qw_changes),
                    total_effort=_estimate_total_effort(qw_changes),
                    patterns_applied=qw_patterns,
                    trade_offs=[
                        "Increased infrastructure cost for additional replicas",
                        "Additional operational complexity from more instances",
                    ],
                    prerequisites=["Basic monitoring and alerting in place"],
                )
            )

        # Proposal 2: High Availability Upgrade (quick wins + critical changes)
        if critical_changes:
            ha_changes = quick_wins[:5] + critical_changes
            ha_impact = sum(c.resilience_impact for c in ha_changes)
            projected = min(100.0, current_score + ha_impact)
            ha_patterns = list(
                {c.pattern for c in ha_changes if c.pattern is not None}
            )
            proposals.append(
                ArchitectureProposal(
                    name="High Availability Upgrade",
                    description=f"Comprehensive changes to reach {target_nines} nines availability. "
                    "Combines quick wins with critical infrastructure changes.",
                    target_nines=target_nines,
                    changes=ha_changes,
                    current_score=round(current_score, 1),
                    projected_score=round(projected, 1),
                    estimated_monthly_cost=_estimate_total_cost(ha_changes),
                    total_effort=_estimate_total_effort(ha_changes),
                    patterns_applied=ha_patterns,
                    trade_offs=[
                        "Significant infrastructure cost increase",
                        "Requires team training on new patterns",
                        "Migration downtime for some changes",
                    ],
                    prerequisites=[
                        "Monitoring and alerting infrastructure",
                        "CI/CD pipeline for automated deployments",
                        "Team familiarity with distributed systems",
                    ],
                )
            )

        # Proposal 3: Full Resilience Architecture (if target >= 4 nines and has components)
        if target_nines >= 4.0 and len(graph.components) > 0:
            full_changes = list(quick_wins) + list(critical_changes)

            # Add multi-region if applicable
            regions = {
                c.region.region
                for c in graph.components.values()
                if c.region.region
            }
            if len(regions) <= 1:
                full_changes.append(
                    ArchitectureChange(
                        change_type="add_pattern",
                        component_id=None,
                        description="Deploy to multiple regions for geographic redundancy",
                        before_state={"regions": len(regions)},
                        after_state={"regions": 2, "mode": "active-active"},
                        pattern=ArchitecturePattern.MULTI_REGION,
                        estimated_cost="$2000+/mo",
                        effort="weeks",
                        resilience_impact=10.0,
                        risk_reduction="Resilience against regional outages",
                    )
                )

            full_impact = sum(c.resilience_impact for c in full_changes)
            projected = min(100.0, current_score + full_impact)
            full_patterns = list(
                {c.pattern for c in full_changes if c.pattern is not None}
            )
            proposals.append(
                ArchitectureProposal(
                    name="Full Resilience Architecture",
                    description=f"Complete architecture redesign targeting {target_nines}+ nines. "
                    "Includes multi-region deployment and all recommended patterns.",
                    target_nines=target_nines,
                    changes=full_changes,
                    current_score=round(current_score, 1),
                    projected_score=round(projected, 1),
                    estimated_monthly_cost=_estimate_total_cost(full_changes),
                    total_effort=_estimate_total_effort(full_changes),
                    patterns_applied=full_patterns,
                    trade_offs=[
                        "Major infrastructure cost increase",
                        "Significant engineering effort over multiple sprints",
                        "Increased operational complexity",
                        "Requires cross-team coordination",
                        "Data consistency challenges in multi-region setup",
                    ],
                    prerequisites=[
                        "Complete monitoring and observability stack",
                        "Mature CI/CD with canary deployments",
                        "Team experience with distributed systems",
                        "Runbooks and incident response procedures",
                        "Load testing framework",
                    ],
                )
            )

        return proposals

    def _generate_assessment(
        self,
        graph: InfraGraph,
        score: float,
        nines: float,
        target_nines: float,
    ) -> str:
        """Generate a natural language assessment of current architecture."""
        n_components = len(graph.components)
        n_deps = len(graph.all_dependency_edges())

        spof_count = sum(
            1
            for c in graph.components.values()
            if c.replicas <= 1 and len(graph.get_dependents(c.id)) > 0
        )

        cb_total = len(graph.all_dependency_edges())
        cb_enabled = sum(
            1 for e in graph.all_dependency_edges() if e.circuit_breaker.enabled
        )

        lines = [
            f"Infrastructure has {n_components} components with {n_deps} dependencies.",
            f"Current resilience score: {score:.1f}/100 ({nines:.2f} nines).",
        ]

        if spof_count > 0:
            lines.append(
                f"WARNING: {spof_count} single point(s) of failure detected."
            )

        if cb_total > 0:
            cb_pct = cb_enabled / cb_total * 100
            lines.append(
                f"Circuit breaker coverage: {cb_enabled}/{cb_total} edges ({cb_pct:.0f}%)."
            )

        if nines < target_nines:
            gap = target_nines - nines
            lines.append(
                f"Gap to target ({target_nines} nines): {gap:.2f} nines improvement needed."
            )
        else:
            lines.append(
                f"Current architecture meets the target of {target_nines} nines."
            )

        return " ".join(lines)

    def _generate_gap_analysis(
        self,
        current_score: float,
        current_nines: float,
        target_score: float,
        target_nines: float,
    ) -> str:
        """Generate gap analysis text."""
        if current_score >= target_score:
            return (
                f"Current architecture ({current_nines:.2f} nines) meets or exceeds "
                f"the target of {target_nines} nines. Focus on maintaining current "
                "resilience and optimizing costs."
            )

        gap_score = target_score - current_score
        gap_nines = target_nines - current_nines
        return (
            f"Score gap: {gap_score:.1f} points ({current_score:.1f} -> {target_score:.1f}). "
            f"Nines gap: {gap_nines:.2f} ({current_nines:.2f} -> {target_nines}). "
            f"This requires reducing failure probability by "
            f"{10**gap_nines:.0f}x through redundancy, circuit breakers, and isolation patterns."
        )

    def _mermaid_node_label(self, comp: Component) -> str:
        """Generate Mermaid node label based on component type."""
        label = comp.name or comp.id
        if comp.replicas > 1:
            label += f" x{comp.replicas}"

        shape = self._mermaid_shape_for_type(comp.type.value)
        return f"{shape[0]}{label}{shape[1]}"

    @staticmethod
    def _mermaid_shape_for_type(comp_type: str) -> tuple[str, str]:
        """Return Mermaid shape delimiters for a component type."""
        if comp_type in ("database",):
            return ("[(", ")]")
        if comp_type in ("queue", "storage"):
            return ("[[", "]]")
        if comp_type in ("cache",):
            return ("((", "))")
        if comp_type in ("load_balancer", "dns"):
            return ("{", "}")
        if comp_type in ("external_api",):
            return (">", "]")
        # Default rectangle
        return ("[", "]")

    def _apply_change(self, graph: InfraGraph, change: ArchitectureChange) -> None:
        """Apply a single architecture change to a graph (in-place)."""
        if change.change_type == "modify_component" and change.component_id:
            comp = graph.get_component(change.component_id)
            if comp is None:
                return
            after = change.after_state
            if "replicas" in after:
                comp.replicas = after["replicas"]
            if "failover_enabled" in after and after["failover_enabled"]:
                comp.failover = FailoverConfig(
                    enabled=True,
                    promotion_time_seconds=after.get(
                        "promotion_time_seconds", 30.0
                    ),
                    health_check_interval_seconds=after.get(
                        "health_check_interval_seconds",
                        comp.failover.health_check_interval_seconds,
                    ),
                    failover_threshold=after.get(
                        "failover_threshold", comp.failover.failover_threshold
                    ),
                )
            if "autoscaling_enabled" in after and after["autoscaling_enabled"]:
                comp.autoscaling = AutoScalingConfig(
                    enabled=True,
                    min_replicas=after.get("min_replicas", comp.replicas),
                    max_replicas=after.get("max_replicas", comp.replicas * 3),
                    scale_up_threshold=after.get(
                        "scale_up_threshold",
                        comp.autoscaling.scale_up_threshold,
                    ),
                )

        elif change.change_type == "modify_dependency" and change.component_id:
            parts = change.component_id.split("->")
            if len(parts) != 2:
                return
            source_id, target_id = parts[0].strip(), parts[1].strip()
            edge = graph.get_dependency_edge(source_id, target_id)
            if edge is None:
                return
            after = change.after_state
            if "circuit_breaker_enabled" in after and after["circuit_breaker_enabled"]:
                edge.circuit_breaker = CircuitBreakerConfig(
                    enabled=True,
                    failure_threshold=after.get("failure_threshold", 5),
                    recovery_timeout_seconds=after.get(
                        "recovery_timeout_seconds", 60.0
                    ),
                )

        elif change.change_type == "add_component" and change.component_id:
            if change.component_id in graph.components:
                return
            after = change.after_state
            comp_type_str = after.get("type", "custom")
            try:
                comp_type = ComponentType(comp_type_str)
            except ValueError:
                comp_type = ComponentType.CUSTOM
            new_comp = Component(
                id=change.component_id,
                name=after.get("name", change.component_id),
                type=comp_type,
                replicas=after.get("replicas", 1),
            )
            graph.add_component(new_comp)

        elif change.change_type == "add_dependency" and change.component_id:
            parts = change.component_id.split("->")
            if len(parts) != 2:
                return
            source_id, target_id = parts[0].strip(), parts[1].strip()
            if source_id in graph.components and target_id in graph.components:
                dep = Dependency(
                    source_id=source_id,
                    target_id=target_id,
                    dependency_type=change.after_state.get(
                        "dependency_type", "requires"
                    ),
                )
                graph.add_dependency(dep)
