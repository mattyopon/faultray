"""Architecture Anti-Pattern Detector.

Detects known architectural anti-patterns in infrastructure graphs,
including god components, circular dependencies, missing circuit breakers,
single availability zones, and more.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import networkx as nx

from faultray.model.components import ComponentType
from faultray.model.graph import InfraGraph


@dataclass
class AntiPattern:
    """A detected anti-pattern in the infrastructure."""

    id: str
    name: str
    severity: str  # "critical", "high", "medium"
    description: str
    affected_components: list[str] = field(default_factory=list)
    recommendation: str = ""
    reference: str = ""


# Severity ordering for filtering
_SEVERITY_ORDER = {"critical": 3, "high": 2, "medium": 1}


class AntiPatternDetector:
    """Detect known architectural anti-patterns in an InfraGraph."""

    def __init__(self, graph: InfraGraph) -> None:
        self.graph = graph

    def detect(self) -> list[AntiPattern]:
        """Detect all anti-patterns and return findings sorted by severity."""
        patterns: list[AntiPattern] = []
        patterns.extend(self._check_god_component())
        patterns.extend(self._check_circular_dependency())
        patterns.extend(self._check_missing_circuit_breaker())
        patterns.extend(self._check_database_direct_access())
        patterns.extend(self._check_single_az())
        patterns.extend(self._check_no_health_check())
        patterns.extend(self._check_thundering_herd())
        patterns.extend(self._check_n_plus_one())
        # Sort by severity descending
        patterns.sort(
            key=lambda p: _SEVERITY_ORDER.get(p.severity, 0), reverse=True
        )
        return patterns

    def detect_by_severity(self, min_severity: str = "medium") -> list[AntiPattern]:
        """Detect anti-patterns at or above the given minimum severity.

        Parameters
        ----------
        min_severity:
            Minimum severity to include: ``"medium"``, ``"high"``, or
            ``"critical"``.
        """
        min_order = _SEVERITY_ORDER.get(min_severity, 1)
        all_patterns = self.detect()
        return [
            p for p in all_patterns
            if _SEVERITY_ORDER.get(p.severity, 0) >= min_order
        ]

    # ------------------------------------------------------------------
    # Individual anti-pattern checks
    # ------------------------------------------------------------------

    def _check_god_component(self) -> list[AntiPattern]:
        """Detect components that >50% of the system depends on (god component)."""
        results: list[AntiPattern] = []
        components = self.graph.components
        if len(components) < 2:
            return results

        threshold = len(components) * 0.5
        for comp_id, comp in components.items():
            dependents = self.graph.get_dependents(comp_id)
            if len(dependents) > threshold:
                results.append(AntiPattern(
                    id="god_component",
                    name="God Component",
                    severity="critical",
                    description=(
                        f"Component '{comp.name}' ({comp_id}) has "
                        f"{len(dependents)} dependents out of "
                        f"{len(components)} total components "
                        f"({len(dependents)/len(components)*100:.0f}%). "
                        "A single point of extreme coupling."
                    ),
                    affected_components=[comp_id] + [d.id for d in dependents],
                    recommendation=(
                        "Split into smaller services or add redundancy. "
                        "Consider introducing a message queue or event bus "
                        "to decouple consumers."
                    ),
                    reference="https://wiki.c2.com/?GodObject",
                ))
        return results

    def _check_circular_dependency(self) -> list[AntiPattern]:
        """Detect circular dependencies in the graph."""
        results: list[AntiPattern] = []
        cycles = _find_cycles(self.graph)
        for cycle in cycles:
            cycle_str = " -> ".join(cycle + [cycle[0]])
            results.append(AntiPattern(
                id="circular_dependency",
                name="Circular Dependency",
                severity="high",
                description=(
                    f"Circular dependency detected: {cycle_str}. "
                    "Components depend on each other in a cycle, which "
                    "can cause deadlocks, startup ordering issues, and "
                    "cascade failures."
                ),
                affected_components=list(cycle),
                recommendation=(
                    "Break the cycle with async communication, an event "
                    "bus, or by extracting shared functionality into a "
                    "separate service."
                ),
                reference="https://en.wikipedia.org/wiki/Circular_dependency",
            ))
        return results

    def _check_missing_circuit_breaker(self) -> list[AntiPattern]:
        """Detect 'requires' dependency edges without circuit breakers."""
        results: list[AntiPattern] = []
        for edge in self.graph.all_dependency_edges():
            if edge.dependency_type == "requires" and not edge.circuit_breaker.enabled:
                results.append(AntiPattern(
                    id="missing_circuit_breaker",
                    name="Missing Circuit Breaker on Critical Path",
                    severity="high",
                    description=(
                        f"Dependency {edge.source_id} -> {edge.target_id} "
                        f"is a 'requires' dependency without a circuit "
                        f"breaker. A failure in {edge.target_id} will "
                        f"cascade directly to {edge.source_id}."
                    ),
                    affected_components=[edge.source_id, edge.target_id],
                    recommendation=(
                        "Enable a circuit breaker on this dependency edge "
                        "to prevent cascade failures. Configure appropriate "
                        "failure_threshold and recovery_timeout."
                    ),
                    reference="https://martinfowler.com/bliki/CircuitBreaker.html",
                ))
        return results

    def _check_database_direct_access(self) -> list[AntiPattern]:
        """Detect app servers accessing databases without connection pooling.

        Checks for app/web servers that directly depend on databases
        with replicas=1 (no connection pool proxy like PgBouncer).
        """
        results: list[AntiPattern] = []
        db_types = {ComponentType.DATABASE}
        app_types = {ComponentType.APP_SERVER, ComponentType.WEB_SERVER}

        for edge in self.graph.all_dependency_edges():
            source = self.graph.get_component(edge.source_id)
            target = self.graph.get_component(edge.target_id)
            if source is None or target is None:
                continue
            if source.type in app_types and target.type in db_types:
                # Count how many app servers hit this DB directly
                direct_apps = [
                    e for e in self.graph.all_dependency_edges()
                    if e.target_id == target.id
                    and self.graph.get_component(e.source_id) is not None
                    and self.graph.get_component(e.source_id).type in app_types
                ]
                if len(direct_apps) > 1:
                    # Multiple app servers hitting the same DB directly
                    affected = [e.source_id for e in direct_apps] + [target.id]
                    # Deduplicate (only add one pattern per DB)
                    already = any(
                        p.id == "database_direct_access" and target.id in p.affected_components
                        for p in results
                    )
                    if not already:
                        results.append(AntiPattern(
                            id="database_direct_access",
                            name="Database Direct Access",
                            severity="medium",
                            description=(
                                f"{len(direct_apps)} app servers access "
                                f"database '{target.name}' ({target.id}) "
                                f"directly. This risks connection exhaustion "
                                f"without a connection pooling proxy."
                            ),
                            affected_components=list(dict.fromkeys(affected)),
                            recommendation=(
                                "Add a connection pooling layer (PgBouncer, "
                                "ProxySQL, etc.) between app servers and "
                                "the database."
                            ),
                            reference="https://www.pgbouncer.org/",
                        ))
        return results

    def _check_single_az(self) -> list[AntiPattern]:
        """Detect all components in a single availability zone."""
        components = list(self.graph.components.values())
        if len(components) < 2:
            return []

        # Collect AZs; components with empty AZ are treated as "unspecified"
        azs = set()
        for comp in components:
            az = comp.region.availability_zone
            if az:
                azs.add(az)

        # If all components have AZ set and they are all the same -> problem
        components_with_az = [c for c in components if c.region.availability_zone]
        if len(components_with_az) == len(components) and len(azs) == 1:
            return [AntiPattern(
                id="single_az",
                name="Single Availability Zone",
                severity="critical",
                description=(
                    f"All {len(components)} components are deployed in a "
                    f"single availability zone ({azs.pop()}). An AZ "
                    f"failure would take down the entire system."
                ),
                affected_components=[c.id for c in components],
                recommendation=(
                    "Distribute components across at least 2 availability "
                    "zones for zone-level redundancy."
                ),
                reference="https://docs.aws.amazon.com/whitepapers/latest/real-time-communication-on-aws/high-availability-and-scalability-on-aws.html",
            )]

        # Also flag if no AZ is set on any component (no AZ awareness at all)
        if not components_with_az:
            return [AntiPattern(
                id="single_az",
                name="Single Availability Zone",
                severity="critical",
                description=(
                    "No availability zone is configured on any component. "
                    "The system has no AZ-level redundancy awareness."
                ),
                affected_components=[c.id for c in components],
                recommendation=(
                    "Configure availability zones on components and "
                    "distribute across at least 2 AZs."
                ),
                reference="https://docs.aws.amazon.com/whitepapers/latest/real-time-communication-on-aws/high-availability-and-scalability-on-aws.html",
            )]

        return []

    def _check_no_health_check(self) -> list[AntiPattern]:
        """Detect load balancers without health checks (failover not enabled)."""
        results: list[AntiPattern] = []
        for comp_id, comp in self.graph.components.items():
            if comp.type == ComponentType.LOAD_BALANCER:
                if not comp.failover.enabled or comp.failover.health_check_interval_seconds <= 0:
                    results.append(AntiPattern(
                        id="no_health_check",
                        name="No Health Check on Load Balancer",
                        severity="high",
                        description=(
                            f"Load balancer '{comp.name}' ({comp_id}) "
                            f"does not have health checks configured. "
                            f"It cannot detect and route around failed "
                            f"backends."
                        ),
                        affected_components=[comp_id],
                        recommendation=(
                            "Enable failover with health_check_interval_seconds "
                            "on the load balancer to detect unhealthy backends."
                        ),
                        reference="https://docs.aws.amazon.com/elasticloadbalancing/latest/application/target-group-health-checks.html",
                    ))
        return results

    def _check_thundering_herd(self) -> list[AntiPattern]:
        """Detect components that may cause thundering herd on restart.

        Flags 'requires' edges where neither retry jitter nor singleflight
        is enabled, meaning simultaneous restarts will flood dependencies.
        """
        results: list[AntiPattern] = []
        components = self.graph.components

        # Look for groups of components of the same type with replicas > 1
        # that depend on the same target without jitter/singleflight
        target_dependents: dict[str, list[str]] = {}
        for edge in self.graph.all_dependency_edges():
            if edge.dependency_type != "requires":
                continue
            target_dependents.setdefault(edge.target_id, []).append(edge.source_id)

        for target_id, source_ids in target_dependents.items():
            if len(source_ids) < 2:
                continue

            # Check if any source lacks jitter on retry and singleflight
            no_jitter_sources = []
            for sid in source_ids:
                comp = components.get(sid)
                edge = self.graph.get_dependency_edge(sid, target_id)
                if comp is None or edge is None:
                    continue
                has_retry_jitter = edge.retry_strategy.enabled and edge.retry_strategy.jitter
                has_singleflight = comp.singleflight.enabled
                if not has_retry_jitter and not has_singleflight:
                    no_jitter_sources.append(sid)

            if len(no_jitter_sources) >= 2:
                target_comp = components.get(target_id)
                target_name = target_comp.name if target_comp else target_id
                results.append(AntiPattern(
                    id="thundering_herd",
                    name="Thundering Herd Risk",
                    severity="medium",
                    description=(
                        f"{len(no_jitter_sources)} components depend on "
                        f"'{target_name}' ({target_id}) without retry "
                        f"jitter or request coalescing. Simultaneous "
                        f"reconnection will flood the target."
                    ),
                    affected_components=no_jitter_sources + [target_id],
                    recommendation=(
                        "Enable retry jitter on dependency edges and/or "
                        "singleflight request coalescing on source "
                        "components to prevent thundering herd."
                    ),
                    reference="https://en.wikipedia.org/wiki/Thundering_herd_problem",
                ))
        return results

    def _check_n_plus_one(self) -> list[AntiPattern]:
        """Detect N+1 dependency: component depends on N identical services
        without a load balancer in front.

        Flags when a component has multiple 'requires' dependencies to
        components of the same type, with no load balancer intermediary.
        """
        results: list[AntiPattern] = []
        components = self.graph.components

        for comp_id, comp in components.items():
            deps = self.graph.get_dependencies(comp_id)
            if len(deps) < 2:
                continue

            # Group dependencies by type
            type_groups: dict[ComponentType, list[str]] = {}
            for dep in deps:
                type_groups.setdefault(dep.type, []).append(dep.id)

            for dep_type, dep_ids in type_groups.items():
                if len(dep_ids) < 2:
                    continue
                # Skip if the source IS a load balancer (that's its job)
                if comp.type == ComponentType.LOAD_BALANCER:
                    continue
                # Skip if target type is load_balancer
                if dep_type == ComponentType.LOAD_BALANCER:
                    continue

                results.append(AntiPattern(
                    id="n_plus_one",
                    name="N+1 Dependency",
                    severity="medium",
                    description=(
                        f"Component '{comp.name}' ({comp_id}) depends on "
                        f"{len(dep_ids)} {dep_type.value} components "
                        f"({', '.join(dep_ids)}) without a load balancer. "
                        f"Client-side load balancing adds complexity and "
                        f"inconsistent behavior."
                    ),
                    affected_components=[comp_id] + dep_ids,
                    recommendation=(
                        "Add a load balancer in front of the identical "
                        "services, or use service mesh for client-side "
                        "load balancing with health checks."
                    ),
                    reference="https://microservices.io/patterns/client-side-discovery.html",
                ))
        return results


def _find_cycles(graph: InfraGraph) -> list[list[str]]:
    """Find all simple cycles in the infrastructure graph."""
    try:
        cycles = list(nx.simple_cycles(graph._graph))
        return cycles
    except Exception:
        return []
