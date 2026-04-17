# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""Service Mesh Analyzer - evaluates infrastructure from a service mesh perspective.

Analyzes traffic management, security policies, observability, and resilience
patterns following Istio/Linkerd/Consul patterns.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum

from faultray.model.components import ComponentType
from faultray.model.graph import InfraGraph

logger = logging.getLogger(__name__)


class MeshPattern(str, Enum):
    """Service mesh patterns that can be detected in infrastructure."""

    SIDECAR_PROXY = "sidecar_proxy"
    CIRCUIT_BREAKER = "circuit_breaker"
    RETRY_BUDGET = "retry_budget"
    TIMEOUT_CHAIN = "timeout_chain"
    MUTUAL_TLS = "mutual_tls"
    TRAFFIC_SPLITTING = "traffic_splitting"
    RATE_LIMITING = "rate_limiting"
    LOAD_BALANCING = "load_balancing"
    HEALTH_CHECKING = "health_checking"
    FAULT_INJECTION = "fault_injection"


class MeshReadiness(str, Enum):
    """Overall mesh readiness level."""

    NOT_READY = "not_ready"
    PARTIAL = "partial"
    READY = "ready"
    ADVANCED = "advanced"


@dataclass
class TrafficPolicy:
    """Traffic management policy for a component."""

    component_id: str
    component_name: str
    has_retry: bool
    has_circuit_breaker: bool
    has_timeout: bool
    has_rate_limit: bool
    timeout_seconds: float
    retry_count: int


@dataclass
class SecurityPolicy:
    """Security policy evaluation for a component."""

    component_id: str
    component_name: str
    mtls_enabled: bool
    auth_enabled: bool
    encrypted: bool
    network_segmented: bool


@dataclass
class ObservabilityScore:
    """Observability assessment for a component."""

    component_id: str
    component_name: str
    has_logging: bool
    has_monitoring: bool
    has_tracing: bool
    score: float


@dataclass
class MeshComponent:
    """Full mesh analysis for a single component."""

    component_id: str
    component_name: str
    component_type: str
    traffic_policy: TrafficPolicy
    security_policy: SecurityPolicy
    observability: ObservabilityScore
    patterns_detected: list[MeshPattern]
    readiness: MeshReadiness


@dataclass
class TimeoutChain:
    """Timeout chain validation result for a dependency path."""

    path: list[str]
    path_names: list[str]
    timeouts: list[float]
    is_valid: bool
    issue: str | None


@dataclass
class MeshReport:
    """Complete service mesh analysis report."""

    components: list[MeshComponent]
    overall_readiness: MeshReadiness
    readiness_score: float
    traffic_management_score: float
    security_score: float
    observability_score: float
    patterns_summary: dict[str, int]
    timeout_chains: list[TimeoutChain]
    recommendations: list[str]
    anti_patterns: list[str]


def _readiness_from_score(score: float) -> MeshReadiness:
    """Determine mesh readiness level from a numeric score."""
    if score > 80:
        return MeshReadiness.ADVANCED
    if score >= 50:
        return MeshReadiness.READY
    if score >= 25:
        return MeshReadiness.PARTIAL
    return MeshReadiness.NOT_READY


class ServiceMeshAnalyzer:
    """Analyzes an infrastructure graph from a service mesh perspective.

    Evaluates traffic management, security policies, observability,
    and resilience patterns following Istio/Linkerd/Consul best practices.
    """

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def analyze(self, graph: InfraGraph) -> MeshReport:
        """Perform a full service mesh analysis on the infrastructure graph."""
        if not graph.components:
            return MeshReport(
                components=[],
                overall_readiness=MeshReadiness.NOT_READY,
                readiness_score=0.0,
                traffic_management_score=0.0,
                security_score=0.0,
                observability_score=0.0,
                patterns_summary={},
                timeout_chains=[],
                recommendations=["No components found in the infrastructure graph."],
                anti_patterns=[],
            )

        mesh_components: list[MeshComponent] = []
        for comp_id in graph.components:
            mc = self.analyze_component(graph, comp_id)
            if mc is not None:
                mesh_components.append(mc)

        # Aggregate scores
        traffic_score = self._compute_traffic_management_score(mesh_components)
        security_score = self._compute_security_score(mesh_components)
        observability_score = self._compute_observability_score(mesh_components)

        readiness_score = (traffic_score + security_score + observability_score) / 3.0
        overall_readiness = _readiness_from_score(readiness_score)

        patterns_summary = self._compute_patterns_summary(mesh_components)
        timeout_chains = self.validate_timeout_chains(graph)
        anti_patterns = self.detect_anti_patterns(graph)
        recommendations = self._generate_recommendations(
            graph, mesh_components, anti_patterns, timeout_chains
        )

        return MeshReport(
            components=mesh_components,
            overall_readiness=overall_readiness,
            readiness_score=round(readiness_score, 1),
            traffic_management_score=round(traffic_score, 1),
            security_score=round(security_score, 1),
            observability_score=round(observability_score, 1),
            patterns_summary=patterns_summary,
            timeout_chains=timeout_chains,
            recommendations=recommendations,
            anti_patterns=anti_patterns,
        )

    def analyze_component(
        self, graph: InfraGraph, component_id: str
    ) -> MeshComponent | None:
        """Analyze a single component for service mesh readiness."""
        comp = graph.get_component(component_id)
        if comp is None:
            return None

        traffic = self._evaluate_traffic_policy(graph, component_id)
        security = self._evaluate_security_policy(graph, component_id)
        observability = self._evaluate_observability(graph, component_id)
        patterns = self._detect_component_patterns(graph, component_id)

        # Component readiness based on sub-scores
        sub_scores: list[float] = []
        # Traffic sub-score
        traffic_hits = sum([
            traffic.has_retry,
            traffic.has_circuit_breaker,
            traffic.has_timeout,
            traffic.has_rate_limit,
        ])
        sub_scores.append(traffic_hits / 4.0 * 100)
        # Security sub-score
        sec_hits = sum([
            security.mtls_enabled,
            security.auth_enabled,
            security.encrypted,
            security.network_segmented,
        ])
        sub_scores.append(sec_hits / 4.0 * 100)
        # Observability sub-score
        sub_scores.append(observability.score)

        avg = sum(sub_scores) / len(sub_scores) if sub_scores else 0.0
        readiness = _readiness_from_score(avg)

        return MeshComponent(
            component_id=component_id,
            component_name=comp.name,
            component_type=comp.type.value,
            traffic_policy=traffic,
            security_policy=security,
            observability=observability,
            patterns_detected=patterns,
            readiness=readiness,
        )

    def detect_patterns(self, graph: InfraGraph) -> dict[str, list[str]]:
        """Detect which mesh patterns each component uses.

        Returns a mapping of component_id -> list of pattern names.
        """
        result: dict[str, list[str]] = {}
        for comp_id in graph.components:
            patterns = self._detect_component_patterns(graph, comp_id)
            result[comp_id] = [p.value for p in patterns]
        return result

    def validate_timeout_chains(self, graph: InfraGraph) -> list[TimeoutChain]:
        """Validate timeout chain correctness across dependency paths.

        The outer service timeout must be greater than the inner service
        timeout plus a safety margin.  If outer <= inner the request will
        time out before the downstream call completes.
        """
        chains: list[TimeoutChain] = []
        margin = 5.0  # seconds safety margin

        # Walk all dependency paths (entry -> leaf)
        entry_nodes = [
            cid
            for cid in graph.components
            if not graph.get_dependents(cid)
        ]
        leaf_nodes = [
            cid
            for cid in graph.components
            if not graph.get_dependencies(cid)
        ]

        for entry in entry_nodes:
            for leaf in leaf_nodes:
                if entry == leaf:
                    continue
                # Use the internal networkx graph to enumerate simple paths
                try:
                    import networkx as nx

                    for path in nx.all_simple_paths(
                        graph._graph, entry, leaf
                    ):
                        if len(path) < 2:
                            continue
                        timeouts = []
                        path_names = []
                        for node_id in path:
                            comp = graph.get_component(node_id)
                            if comp is not None:
                                timeouts.append(comp.capacity.timeout_seconds)
                                path_names.append(comp.name)
                            else:
                                timeouts.append(0.0)
                                path_names.append(node_id)

                        is_valid = True
                        issue: str | None = None

                        # Check that each outer timeout > inner + margin
                        for i in range(len(timeouts) - 1):
                            outer = timeouts[i]
                            inner = timeouts[i + 1]
                            if outer <= inner + margin:
                                is_valid = False
                                issue = (
                                    f"Timeout at '{path_names[i]}' "
                                    f"({outer}s) <= timeout at "
                                    f"'{path_names[i + 1]}' ({inner}s) "
                                    f"+ {margin}s margin"
                                )
                                break

                        chains.append(
                            TimeoutChain(
                                path=list(path),
                                path_names=path_names,
                                timeouts=timeouts,
                                is_valid=is_valid,
                                issue=issue,
                            )
                        )
                except Exception as e:
                    logger.warning(
                        "Failed to analyze timeout chain for path %s -> %s: %s",
                        entry, leaf, e,
                    )

        return chains

    def detect_anti_patterns(self, graph: InfraGraph) -> list[str]:
        """Detect common service mesh anti-patterns in the infrastructure."""
        anti_patterns: list[str] = []

        # 1. Retry storm: multiple retry layers without budget limits
        for comp_id, comp in graph.components.items():
            deps = graph.get_dependencies(comp_id)
            retry_layers = 0
            has_budget = True
            for dep_comp in deps:
                edge = graph.get_dependency_edge(comp_id, dep_comp.id)
                if edge and edge.retry_strategy.enabled:
                    retry_layers += 1
                    if edge.retry_strategy.retry_budget_per_second <= 0:
                        has_budget = False
            if retry_layers >= 2 and not has_budget:
                anti_patterns.append(
                    f"Retry storm: '{comp.name}' has {retry_layers} retry "
                    f"layers without budget limits"
                )

        # 2. Timeout cascade: outer timeout <= inner timeout
        timeout_chains = self.validate_timeout_chains(graph)
        for chain in timeout_chains:
            if not chain.is_valid and chain.issue:
                anti_patterns.append(f"Timeout cascade: {chain.issue}")

        # 3. Missing circuit breaker: high-dependency components without CB
        for comp_id, comp in graph.components.items():
            dependents = graph.get_dependents(comp_id)
            if len(dependents) >= 3:
                # Check if all incoming edges have circuit breakers
                missing_cb = False
                for dep_comp in dependents:
                    edge = graph.get_dependency_edge(dep_comp.id, comp_id)
                    if edge and not edge.circuit_breaker.enabled:
                        missing_cb = True
                        break
                if missing_cb:
                    anti_patterns.append(
                        f"Missing circuit breaker: '{comp.name}' has "
                        f"{len(dependents)} dependents but lacks circuit "
                        f"breaker protection on some edges"
                    )

        # 4. Unprotected external: external APIs without rate limiting or CB
        for comp_id, comp in graph.components.items():
            if comp.type == ComponentType.EXTERNAL_API:
                has_protection = False
                # Check incoming edges for CB
                dependents = graph.get_dependents(comp_id)
                for dep_comp in dependents:
                    edge = graph.get_dependency_edge(dep_comp.id, comp_id)
                    if edge and edge.circuit_breaker.enabled:
                        has_protection = True
                        break
                if not has_protection and not comp.security.rate_limiting:
                    anti_patterns.append(
                        f"Unprotected external: '{comp.name}' is an external "
                        f"API without rate limiting or circuit breaker"
                    )

        # 5. Inconsistent mTLS: partial mesh encryption
        mtls_components = []
        non_mtls_components = []
        for comp_id, comp in graph.components.items():
            if comp.security.encryption_in_transit and comp.security.auth_required:
                mtls_components.append(comp.name)
            else:
                non_mtls_components.append(comp.name)
        if mtls_components and non_mtls_components:
            anti_patterns.append(
                f"Inconsistent mTLS: {len(mtls_components)} component(s) "
                f"have mTLS enabled but {len(non_mtls_components)} do not "
                f"({', '.join(non_mtls_components[:3])})"
            )

        return anti_patterns

    def get_mesh_migration_plan(self, graph: InfraGraph) -> list[dict]:
        """Suggest migration steps to achieve full service mesh adoption.

        Returns a prioritized list of migration steps, each containing:
        - step: step number
        - phase: migration phase name
        - description: what to do
        - components: affected component IDs
        - priority: high/medium/low
        """
        if not graph.components:
            return []

        steps: list[dict] = []
        step_num = 0

        # Phase 1: Enable mTLS across all components
        no_mtls = [
            cid
            for cid, c in graph.components.items()
            if not (c.security.encryption_in_transit and c.security.auth_required)
        ]
        if no_mtls:
            step_num += 1
            steps.append({
                "step": step_num,
                "phase": "mutual_tls",
                "description": "Enable mutual TLS (mTLS) for encrypted service-to-service communication",
                "components": no_mtls,
                "priority": "high",
            })

        # Phase 2: Add circuit breakers to all dependency edges
        edges_without_cb: list[str] = []
        for edge in graph.all_dependency_edges():
            if not edge.circuit_breaker.enabled:
                edges_without_cb.append(f"{edge.source_id} -> {edge.target_id}")
        if edges_without_cb:
            step_num += 1
            steps.append({
                "step": step_num,
                "phase": "circuit_breakers",
                "description": "Add circuit breakers to all dependency edges to prevent cascade failures",
                "components": edges_without_cb,
                "priority": "high",
            })

        # Phase 3: Configure retry budgets
        edges_without_retry: list[str] = []
        for edge in graph.all_dependency_edges():
            if not edge.retry_strategy.enabled:
                edges_without_retry.append(
                    f"{edge.source_id} -> {edge.target_id}"
                )
        if edges_without_retry:
            step_num += 1
            steps.append({
                "step": step_num,
                "phase": "retry_budgets",
                "description": "Configure retry strategies with budget limits on all dependency edges",
                "components": edges_without_retry,
                "priority": "medium",
            })

        # Phase 4: Add rate limiting
        no_rate_limit = [
            cid
            for cid, c in graph.components.items()
            if not c.security.rate_limiting
        ]
        if no_rate_limit:
            step_num += 1
            steps.append({
                "step": step_num,
                "phase": "rate_limiting",
                "description": "Enable rate limiting to protect services from traffic spikes",
                "components": no_rate_limit,
                "priority": "medium",
            })

        # Phase 5: Validate timeout chains
        invalid_chains = [
            c for c in self.validate_timeout_chains(graph) if not c.is_valid
        ]
        if invalid_chains:
            step_num += 1
            affected = set()
            for chain in invalid_chains:
                affected.update(chain.path)
            steps.append({
                "step": step_num,
                "phase": "timeout_tuning",
                "description": "Fix timeout chains so outer timeouts exceed inner timeouts with margin",
                "components": sorted(affected),
                "priority": "high",
            })

        # Phase 6: Enable observability (logging, monitoring, tracing)
        no_observability = [
            cid
            for cid, c in graph.components.items()
            if not c.security.log_enabled
        ]
        if no_observability:
            step_num += 1
            steps.append({
                "step": step_num,
                "phase": "observability",
                "description": "Enable logging, monitoring, and distributed tracing for all services",
                "components": no_observability,
                "priority": "medium",
            })

        # Phase 7: Health checking and failover
        no_health_check = [
            cid
            for cid, c in graph.components.items()
            if not c.failover.enabled
        ]
        if no_health_check:
            step_num += 1
            steps.append({
                "step": step_num,
                "phase": "health_checking",
                "description": "Configure health checks and failover for resilient service discovery",
                "components": no_health_check,
                "priority": "low",
            })

        return steps

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _evaluate_traffic_policy(
        self, graph: InfraGraph, component_id: str
    ) -> TrafficPolicy:
        """Build a TrafficPolicy for the given component."""
        comp = graph.get_component(component_id)
        if comp is None:
            return TrafficPolicy(
                component_id=component_id,
                component_name=component_id,
                has_retry=False,
                has_circuit_breaker=False,
                has_timeout=False,
                has_rate_limit=False,
                timeout_seconds=0.0,
                retry_count=0,
            )

        has_retry = False
        has_cb = False
        retry_count = 0

        # Check outgoing edges for retry / circuit breaker config
        deps = graph.get_dependencies(component_id)
        for dep_comp in deps:
            edge = graph.get_dependency_edge(component_id, dep_comp.id)
            if edge is not None:
                if edge.retry_strategy.enabled:
                    has_retry = True
                    retry_count = max(retry_count, edge.retry_strategy.max_retries)
                if edge.circuit_breaker.enabled:
                    has_cb = True

        # Also check incoming edges (other components calling us with CB/retry)
        dependents = graph.get_dependents(component_id)
        for dep_comp in dependents:
            edge = graph.get_dependency_edge(dep_comp.id, component_id)
            if edge is not None:
                if edge.circuit_breaker.enabled:
                    has_cb = True
                if edge.retry_strategy.enabled:
                    has_retry = True
                    retry_count = max(retry_count, edge.retry_strategy.max_retries)

        has_timeout = comp.capacity.timeout_seconds > 0
        has_rate_limit = comp.security.rate_limiting

        return TrafficPolicy(
            component_id=component_id,
            component_name=comp.name,
            has_retry=has_retry,
            has_circuit_breaker=has_cb,
            has_timeout=has_timeout,
            has_rate_limit=has_rate_limit,
            timeout_seconds=comp.capacity.timeout_seconds,
            retry_count=retry_count,
        )

    def _evaluate_security_policy(
        self, graph: InfraGraph, component_id: str
    ) -> SecurityPolicy:
        """Build a SecurityPolicy for the given component."""
        comp = graph.get_component(component_id)
        if comp is None:
            return SecurityPolicy(
                component_id=component_id,
                component_name=component_id,
                mtls_enabled=False,
                auth_enabled=False,
                encrypted=False,
                network_segmented=False,
            )

        sec = comp.security
        mtls = sec.encryption_in_transit and sec.auth_required
        return SecurityPolicy(
            component_id=component_id,
            component_name=comp.name,
            mtls_enabled=mtls,
            auth_enabled=sec.auth_required,
            encrypted=sec.encryption_in_transit,
            network_segmented=sec.network_segmented,
        )

    def _evaluate_observability(
        self, graph: InfraGraph, component_id: str
    ) -> ObservabilityScore:
        """Build an ObservabilityScore for the given component."""
        comp = graph.get_component(component_id)
        if comp is None:
            return ObservabilityScore(
                component_id=component_id,
                component_name=component_id,
                has_logging=False,
                has_monitoring=False,
                has_tracing=False,
                score=0.0,
            )

        sec = comp.security
        has_logging = sec.log_enabled
        has_monitoring = sec.ids_monitored
        has_tracing = sec.encryption_in_transit  # proxy for tracing via sidecar

        hits = sum([has_logging, has_monitoring, has_tracing])
        score = hits / 3.0 * 100.0

        return ObservabilityScore(
            component_id=component_id,
            component_name=comp.name,
            has_logging=has_logging,
            has_monitoring=has_monitoring,
            has_tracing=has_tracing,
            score=round(score, 1),
        )

    def _detect_component_patterns(
        self, graph: InfraGraph, component_id: str
    ) -> list[MeshPattern]:
        """Detect mesh patterns for a single component."""
        comp = graph.get_component(component_id)
        if comp is None:
            return []

        patterns: list[MeshPattern] = []

        has_retry = False
        has_cb = False

        # Outgoing dependency edges
        deps = graph.get_dependencies(component_id)
        for dep_comp in deps:
            edge = graph.get_dependency_edge(component_id, dep_comp.id)
            if edge is not None:
                if edge.circuit_breaker.enabled:
                    has_cb = True
                if edge.retry_strategy.enabled:
                    has_retry = True

        # Incoming dependency edges
        dependents = graph.get_dependents(component_id)
        for dep_comp in dependents:
            edge = graph.get_dependency_edge(dep_comp.id, component_id)
            if edge is not None:
                if edge.circuit_breaker.enabled:
                    has_cb = True
                if edge.retry_strategy.enabled:
                    has_retry = True

        # SIDECAR_PROXY: component has both retry and circuit breaker
        if has_retry and has_cb:
            patterns.append(MeshPattern.SIDECAR_PROXY)

        # CIRCUIT_BREAKER
        if has_cb:
            patterns.append(MeshPattern.CIRCUIT_BREAKER)

        # RETRY_BUDGET
        if has_retry:
            patterns.append(MeshPattern.RETRY_BUDGET)

        # TIMEOUT_CHAIN
        if comp.capacity.timeout_seconds > 0:
            patterns.append(MeshPattern.TIMEOUT_CHAIN)

        # MUTUAL_TLS
        if comp.security.encryption_in_transit and comp.security.auth_required:
            patterns.append(MeshPattern.MUTUAL_TLS)

        # TRAFFIC_SPLITTING: load balancer type with multiple targets
        if comp.type == ComponentType.LOAD_BALANCER and len(deps) > 1:
            patterns.append(MeshPattern.TRAFFIC_SPLITTING)

        # RATE_LIMITING
        if comp.security.rate_limiting:
            patterns.append(MeshPattern.RATE_LIMITING)

        # LOAD_BALANCING: load balancer type or replicas > 1
        if comp.type == ComponentType.LOAD_BALANCER or comp.replicas > 1:
            patterns.append(MeshPattern.LOAD_BALANCING)

        # HEALTH_CHECKING: failover config with health_check_interval
        if comp.failover.enabled:
            patterns.append(MeshPattern.HEALTH_CHECKING)

        # FAULT_INJECTION: always False (needs explicit config)
        # Not appended

        return patterns

    def _compute_traffic_management_score(
        self, components: list[MeshComponent]
    ) -> float:
        """Aggregate traffic management score across all components (0-100)."""
        if not components:
            return 0.0
        total = 0.0
        for mc in components:
            tp = mc.traffic_policy
            hits = sum([
                tp.has_retry,
                tp.has_circuit_breaker,
                tp.has_timeout,
                tp.has_rate_limit,
            ])
            total += hits / 4.0 * 100.0
        return total / len(components)

    def _compute_security_score(
        self, components: list[MeshComponent]
    ) -> float:
        """Aggregate security score across all components (0-100)."""
        if not components:
            return 0.0
        total = 0.0
        for mc in components:
            sp = mc.security_policy
            hits = sum([
                sp.mtls_enabled,
                sp.auth_enabled,
                sp.encrypted,
                sp.network_segmented,
            ])
            total += hits / 4.0 * 100.0
        return total / len(components)

    def _compute_observability_score(
        self, components: list[MeshComponent]
    ) -> float:
        """Aggregate observability score across all components (0-100)."""
        if not components:
            return 0.0
        total = sum(mc.observability.score for mc in components)
        return total / len(components)

    def _compute_patterns_summary(
        self, components: list[MeshComponent]
    ) -> dict[str, int]:
        """Count how many components use each pattern."""
        summary: dict[str, int] = {}
        for mc in components:
            for p in mc.patterns_detected:
                summary[p.value] = summary.get(p.value, 0) + 1
        return summary

    def _generate_recommendations(
        self,
        graph: InfraGraph,
        components: list[MeshComponent],
        anti_patterns: list[str],
        timeout_chains: list[TimeoutChain],
    ) -> list[str]:
        """Generate actionable recommendations for mesh adoption."""
        recommendations: list[str] = []

        # Check for missing circuit breakers
        no_cb = [
            mc.component_name
            for mc in components
            if not mc.traffic_policy.has_circuit_breaker
        ]
        if no_cb:
            recommendations.append(
                f"Enable circuit breakers for: {', '.join(no_cb[:5])}"
            )

        # Check for missing mTLS
        no_mtls = [
            mc.component_name
            for mc in components
            if not mc.security_policy.mtls_enabled
        ]
        if no_mtls:
            recommendations.append(
                f"Enable mutual TLS for: {', '.join(no_mtls[:5])}"
            )

        # Check for missing observability
        low_obs = [
            mc.component_name
            for mc in components
            if mc.observability.score < 50.0
        ]
        if low_obs:
            recommendations.append(
                f"Improve observability (logging/monitoring/tracing) for: "
                f"{', '.join(low_obs[:5])}"
            )

        # Check for missing rate limiting
        no_rl = [
            mc.component_name
            for mc in components
            if not mc.traffic_policy.has_rate_limit
        ]
        if no_rl:
            recommendations.append(
                f"Enable rate limiting for: {', '.join(no_rl[:5])}"
            )

        # Invalid timeout chains
        invalid_chains = [tc for tc in timeout_chains if not tc.is_valid]
        if invalid_chains:
            recommendations.append(
                f"Fix {len(invalid_chains)} invalid timeout chain(s) where "
                f"outer timeouts do not exceed inner timeouts"
            )

        # Anti-pattern warnings
        for ap in anti_patterns:
            recommendations.append(f"Fix anti-pattern: {ap}")

        return recommendations
