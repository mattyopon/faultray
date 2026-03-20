# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Business Source License 1.1. See LICENSE file for details.

"""Service Mesh Analyzer - deep analysis of service mesh configurations and resilience.

Analyzes mesh topologies (sidecar proxy, per-node, ambient), traffic management,
mTLS / SPIFFE identity, retry policy evaluation, circuit breaker configuration,
load balancing strategies, observability gaps, control plane resilience,
data plane saturation, and policy enforcement.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from faultray.model.components import Component, ComponentType
from faultray.model.graph import InfraGraph


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class MeshTopology(str, Enum):
    """Service mesh deployment topology."""

    SIDECAR_PROXY = "sidecar_proxy"       # Istio/Envoy per-pod sidecar
    PER_NODE = "per_node"                 # Linkerd per-node DaemonSet
    AMBIENT = "ambient"                   # Istio ambient mesh (no sidecar)
    NONE = "none"                         # No mesh detected


class LoadBalancingStrategy(str, Enum):
    """Load balancing strategies used in service mesh."""

    ROUND_ROBIN = "round_robin"
    LEAST_CONNECTIONS = "least_connections"
    CONSISTENT_HASHING = "consistent_hashing"
    LOCALITY_AWARE = "locality_aware"
    RANDOM = "random"
    UNKNOWN = "unknown"


class BackoffStrategy(str, Enum):
    """Retry backoff strategy types."""

    FIXED = "fixed"
    EXPONENTIAL = "exponential"
    LINEAR = "linear"
    NONE = "none"


class TrafficAction(str, Enum):
    """Traffic management action types."""

    ROUTE = "route"
    SPLIT = "split"
    MIRROR = "mirror"
    FAULT_INJECT = "fault_inject"
    ABORT = "abort"
    DELAY = "delay"


class ObservabilitySignal(str, Enum):
    """Observability signal types."""

    METRICS = "metrics"
    TRACING = "tracing"
    LOGGING = "logging"
    PROFILING = "profiling"


class PolicyEnforcementLevel(str, Enum):
    """Authorization policy enforcement levels."""

    STRICT = "strict"
    PERMISSIVE = "permissive"
    DISABLED = "disabled"


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


class MeshTopologyResult(BaseModel):
    """Result of mesh topology detection for a component."""

    component_id: str
    topology: MeshTopology = MeshTopology.NONE
    proxy_type: str = ""
    proxy_version: str = ""
    resource_overhead_mb: float = Field(default=0.0, ge=0.0)
    resource_overhead_cpu_percent: float = Field(default=0.0, ge=0.0)


class TrafficRule(BaseModel):
    """A traffic management rule applied to a service pair."""

    source_id: str
    target_id: str
    action: TrafficAction
    weight: float = Field(default=100.0, ge=0.0, le=100.0)
    match_headers: dict[str, str] = Field(default_factory=dict)
    fault_percent: float = Field(default=0.0, ge=0.0, le=100.0)
    delay_ms: float = Field(default=0.0, ge=0.0)
    mirror_percent: float = Field(default=0.0, ge=0.0, le=100.0)


class TrafficManagementReport(BaseModel):
    """Report on traffic management configuration."""

    rules: list[TrafficRule] = Field(default_factory=list)
    has_traffic_splitting: bool = False
    has_mirroring: bool = False
    has_fault_injection: bool = False
    split_targets: dict[str, list[dict[str, Any]]] = Field(default_factory=dict)
    coverage_percent: float = Field(default=0.0, ge=0.0, le=100.0)


class MTLSStatus(BaseModel):
    """mTLS analysis result for a service pair or component."""

    component_id: str
    mtls_enabled: bool = False
    trust_domain: str = ""
    spiffe_id: str = ""
    cert_rotation_hours: float = Field(default=0.0, ge=0.0)
    cert_expiry_warning: bool = False
    trust_domain_boundary_crossed: bool = False


class MTLSReport(BaseModel):
    """Aggregate mTLS analysis report."""

    statuses: list[MTLSStatus] = Field(default_factory=list)
    overall_mtls_coverage: float = Field(default=0.0, ge=0.0, le=100.0)
    trust_domains: list[str] = Field(default_factory=list)
    cross_domain_pairs: list[tuple[str, str]] = Field(default_factory=list)
    cert_rotation_issues: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)


class RetryPolicyEvaluation(BaseModel):
    """Evaluation of retry policies across the mesh."""

    component_id: str
    retry_enabled: bool = False
    max_retries: int = 0
    backoff_strategy: BackoffStrategy = BackoffStrategy.NONE
    initial_delay_ms: float = 0.0
    max_delay_ms: float = 0.0
    retry_budget_per_second: float = 0.0
    has_budget_limit: bool = False
    storm_risk: float = Field(default=0.0, ge=0.0, le=1.0)


class RetryPolicyReport(BaseModel):
    """Aggregate retry policy report."""

    evaluations: list[RetryPolicyEvaluation] = Field(default_factory=list)
    retry_storm_risk: float = Field(default=0.0, ge=0.0, le=1.0)
    max_amplification_factor: float = Field(default=1.0, ge=1.0)
    services_without_budget: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)


class CircuitBreakerPairConfig(BaseModel):
    """Circuit breaker configuration for a service pair."""

    source_id: str
    target_id: str
    enabled: bool = False
    failure_threshold: int = 0
    recovery_timeout_seconds: float = 0.0
    half_open_max_requests: int = 0
    success_threshold: int = 0
    effectiveness_score: float = Field(default=0.0, ge=0.0, le=100.0)


class CircuitBreakerReport(BaseModel):
    """Aggregate circuit breaker configuration report."""

    pairs: list[CircuitBreakerPairConfig] = Field(default_factory=list)
    coverage_percent: float = Field(default=0.0, ge=0.0, le=100.0)
    misconfigured_pairs: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)


class LoadBalancingAnalysis(BaseModel):
    """Load balancing strategy analysis for a component."""

    component_id: str
    strategy: LoadBalancingStrategy = LoadBalancingStrategy.UNKNOWN
    replicas: int = 1
    locality_aware: bool = False
    sticky_sessions: bool = False
    health_check_enabled: bool = False
    effectiveness_score: float = Field(default=0.0, ge=0.0, le=100.0)


class LoadBalancingReport(BaseModel):
    """Aggregate load balancing analysis report."""

    analyses: list[LoadBalancingAnalysis] = Field(default_factory=list)
    strategy_distribution: dict[str, int] = Field(default_factory=dict)
    recommendations: list[str] = Field(default_factory=list)


class ObservabilityGap(BaseModel):
    """An identified gap in observability coverage."""

    component_id: str
    missing_signals: list[ObservabilitySignal] = Field(default_factory=list)
    has_metrics: bool = False
    has_tracing: bool = False
    has_logging: bool = False
    coverage_score: float = Field(default=0.0, ge=0.0, le=100.0)


class ObservabilityGapReport(BaseModel):
    """Report on observability coverage and gaps."""

    gaps: list[ObservabilityGap] = Field(default_factory=list)
    overall_coverage: float = Field(default=0.0, ge=0.0, le=100.0)
    fully_covered_count: int = 0
    partially_covered_count: int = 0
    uncovered_count: int = 0
    recommendations: list[str] = Field(default_factory=list)


class ControlPlaneResilienceResult(BaseModel):
    """Result of control plane resilience analysis."""

    is_highly_available: bool = False
    replica_count: int = 1
    failover_capable: bool = False
    last_known_config_survives: bool = True
    cert_rotation_blocked: bool = True
    estimated_impact_percent: float = Field(default=0.0, ge=0.0, le=100.0)
    degraded_features: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)


class DataPlaneSaturationResult(BaseModel):
    """Result of data plane saturation analysis."""

    component_id: str
    sidecar_cpu_percent: float = Field(default=0.0, ge=0.0)
    sidecar_memory_mb: float = Field(default=0.0, ge=0.0)
    connection_pool_usage_percent: float = Field(default=0.0, ge=0.0, le=100.0)
    connection_pool_exhausted: bool = False
    is_saturated: bool = False
    saturation_score: float = Field(default=0.0, ge=0.0, le=100.0)


class DataPlaneSaturationReport(BaseModel):
    """Aggregate data plane saturation report."""

    results: list[DataPlaneSaturationResult] = Field(default_factory=list)
    saturated_count: int = 0
    near_saturation_count: int = 0
    total_sidecar_memory_mb: float = Field(default=0.0, ge=0.0)
    total_sidecar_cpu_percent: float = Field(default=0.0, ge=0.0)
    recommendations: list[str] = Field(default_factory=list)


class PolicyEnforcementResult(BaseModel):
    """Result of policy enforcement analysis for a component."""

    component_id: str
    auth_policy_level: PolicyEnforcementLevel = PolicyEnforcementLevel.DISABLED
    rate_limiting_enabled: bool = False
    rate_limit_rps: float = 0.0
    network_policy_applied: bool = False
    enforcement_score: float = Field(default=0.0, ge=0.0, le=100.0)


class PolicyEnforcementReport(BaseModel):
    """Aggregate policy enforcement report."""

    results: list[PolicyEnforcementResult] = Field(default_factory=list)
    strict_count: int = 0
    permissive_count: int = 0
    disabled_count: int = 0
    overall_enforcement_score: float = Field(default=0.0, ge=0.0, le=100.0)
    recommendations: list[str] = Field(default_factory=list)


class ServiceMeshAnalysisReport(BaseModel):
    """Comprehensive service mesh analysis report."""

    timestamp: str = ""
    total_services: int = 0
    topology: TrafficManagementReport = Field(default_factory=TrafficManagementReport)
    mtls: MTLSReport = Field(default_factory=MTLSReport)
    retry_policy: RetryPolicyReport = Field(default_factory=RetryPolicyReport)
    circuit_breakers: CircuitBreakerReport = Field(default_factory=CircuitBreakerReport)
    load_balancing: LoadBalancingReport = Field(default_factory=LoadBalancingReport)
    observability: ObservabilityGapReport = Field(default_factory=ObservabilityGapReport)
    control_plane: ControlPlaneResilienceResult = Field(
        default_factory=ControlPlaneResilienceResult
    )
    data_plane: DataPlaneSaturationReport = Field(
        default_factory=DataPlaneSaturationReport
    )
    policy_enforcement: PolicyEnforcementReport = Field(
        default_factory=PolicyEnforcementReport
    )
    overall_score: float = Field(default=0.0, ge=0.0, le=100.0)
    recommendations: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_SIDECAR_MEMORY_MB = 50.0
_SIDECAR_CPU_PERCENT = 1.5
_PER_NODE_MEMORY_MB = 80.0
_PER_NODE_CPU_PERCENT = 2.0
_AMBIENT_MEMORY_MB = 10.0
_AMBIENT_CPU_PERCENT = 0.5

_DEFAULT_CERT_ROTATION_HOURS = 24.0
_CERT_EXPIRY_WARNING_HOURS = 4.0

_TOPOLOGY_OVERHEAD: dict[MeshTopology, tuple[float, float]] = {
    MeshTopology.SIDECAR_PROXY: (_SIDECAR_MEMORY_MB, _SIDECAR_CPU_PERCENT),
    MeshTopology.PER_NODE: (_PER_NODE_MEMORY_MB, _PER_NODE_CPU_PERCENT),
    MeshTopology.AMBIENT: (_AMBIENT_MEMORY_MB, _AMBIENT_CPU_PERCENT),
    MeshTopology.NONE: (0.0, 0.0),
}


def _clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    """Clamp *value* between *lo* and *hi*."""
    return max(lo, min(hi, value))


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class ServiceMeshConfigAnalyzer:
    """Stateless engine for deep service mesh configuration analysis.

    Analyzes mesh topologies, traffic management, mTLS, retry policies,
    circuit breakers, load balancing, observability gaps, control plane
    resilience, data plane saturation, and policy enforcement.
    """

    # -- full analysis ------------------------------------------------------

    def analyze(
        self,
        graph: InfraGraph,
        topology: MeshTopology = MeshTopology.SIDECAR_PROXY,
        traffic_rules: list[TrafficRule] | None = None,
        trust_domain: str = "cluster.local",
        cert_rotation_hours: float = _DEFAULT_CERT_ROTATION_HOURS,
    ) -> ServiceMeshAnalysisReport:
        """Perform comprehensive service mesh analysis."""
        if not graph.components:
            return ServiceMeshAnalysisReport(
                timestamp=datetime.now(timezone.utc).isoformat(),
                total_services=0,
                overall_score=0.0,
                recommendations=["No services found in graph."],
            )

        traffic_rules = traffic_rules or []
        total = len(graph.components)

        traffic_report = self.analyze_traffic_management(graph, traffic_rules)
        mtls_report = self.analyze_mtls(graph, trust_domain, cert_rotation_hours)
        retry_report = self.analyze_retry_policies(graph)
        cb_report = self.analyze_circuit_breakers(graph)
        lb_report = self.analyze_load_balancing(graph)
        obs_report = self.analyze_observability_gaps(graph)
        cp_report = self.analyze_control_plane_resilience(graph)
        dp_report = self.analyze_data_plane_saturation(graph, topology)
        pe_report = self.analyze_policy_enforcement(graph)

        # Weighted overall score
        weights = {
            "mtls": 0.15,
            "retry": 0.10,
            "cb": 0.15,
            "lb": 0.10,
            "obs": 0.15,
            "cp": 0.10,
            "dp": 0.10,
            "pe": 0.15,
        }
        scores = {
            "mtls": mtls_report.overall_mtls_coverage,
            "retry": (1.0 - retry_report.retry_storm_risk) * 100.0,
            "cb": cb_report.coverage_percent,
            "lb": (
                sum(a.effectiveness_score for a in lb_report.analyses) / total
                if total > 0
                else 0.0
            ),
            "obs": obs_report.overall_coverage,
            "cp": 100.0 - cp_report.estimated_impact_percent,
            "dp": 100.0 - (
                sum(r.saturation_score for r in dp_report.results) / total
                if total > 0
                else 0.0
            ),
            "pe": pe_report.overall_enforcement_score,
        }
        overall = sum(weights[k] * scores[k] for k in weights)
        overall = _clamp(overall)

        # Aggregate recommendations
        all_recs: list[str] = []
        all_recs.extend(mtls_report.recommendations)
        all_recs.extend(retry_report.recommendations)
        all_recs.extend(cb_report.recommendations)
        all_recs.extend(lb_report.recommendations)
        all_recs.extend(obs_report.recommendations)
        all_recs.extend(cp_report.recommendations)
        all_recs.extend(dp_report.recommendations)
        all_recs.extend(pe_report.recommendations)
        # Deduplicate
        seen: set[str] = set()
        unique_recs: list[str] = []
        for r in all_recs:
            if r not in seen:
                seen.add(r)
                unique_recs.append(r)

        return ServiceMeshAnalysisReport(
            timestamp=datetime.now(timezone.utc).isoformat(),
            total_services=total,
            topology=traffic_report,
            mtls=mtls_report,
            retry_policy=retry_report,
            circuit_breakers=cb_report,
            load_balancing=lb_report,
            observability=obs_report,
            control_plane=cp_report,
            data_plane=dp_report,
            policy_enforcement=pe_report,
            overall_score=round(overall, 1),
            recommendations=unique_recs,
        )

    # -- traffic management -------------------------------------------------

    def analyze_traffic_management(
        self,
        graph: InfraGraph,
        rules: list[TrafficRule],
    ) -> TrafficManagementReport:
        """Analyze traffic management rules."""
        if not graph.components:
            return TrafficManagementReport()

        has_splitting = False
        has_mirroring = False
        has_fault_injection = False
        split_targets: dict[str, list[dict[str, Any]]] = {}

        for rule in rules:
            if rule.action == TrafficAction.SPLIT:
                has_splitting = True
                split_targets.setdefault(rule.source_id, []).append(
                    {"target_id": rule.target_id, "weight": rule.weight}
                )
            elif rule.action == TrafficAction.MIRROR:
                has_mirroring = True
            elif rule.action in (TrafficAction.FAULT_INJECT, TrafficAction.ABORT, TrafficAction.DELAY):
                has_fault_injection = True

        # Coverage: fraction of edges covered by at least one rule
        all_edges = graph.all_dependency_edges()
        edge_pairs = {(e.source_id, e.target_id) for e in all_edges}
        rule_pairs = {(r.source_id, r.target_id) for r in rules}
        covered = edge_pairs & rule_pairs
        coverage = (len(covered) / len(edge_pairs) * 100.0) if edge_pairs else 0.0

        return TrafficManagementReport(
            rules=rules,
            has_traffic_splitting=has_splitting,
            has_mirroring=has_mirroring,
            has_fault_injection=has_fault_injection,
            split_targets=split_targets,
            coverage_percent=round(_clamp(coverage), 1),
        )

    # -- mTLS analysis ------------------------------------------------------

    def analyze_mtls(
        self,
        graph: InfraGraph,
        trust_domain: str = "cluster.local",
        cert_rotation_hours: float = _DEFAULT_CERT_ROTATION_HOURS,
    ) -> MTLSReport:
        """Analyze mTLS configuration across the mesh."""
        if not graph.components:
            return MTLSReport(recommendations=["No services to analyze."])

        statuses: list[MTLSStatus] = []
        enabled_count = 0
        trust_domains: set[str] = set()
        cross_domain: list[tuple[str, str]] = []
        cert_issues: list[str] = []

        for cid, comp in graph.components.items():
            sec = comp.security
            mtls_on = sec.encryption_in_transit and sec.auth_required
            comp_domain = comp.parameters.get("trust_domain", trust_domain)
            if isinstance(comp_domain, (int, float)):
                comp_domain = str(comp_domain)
            spiffe_id = f"spiffe://{comp_domain}/ns/default/sa/{cid}" if mtls_on else ""
            cert_warning = cert_rotation_hours <= _CERT_EXPIRY_WARNING_HOURS
            boundary_crossed = False

            trust_domains.add(str(comp_domain))

            if mtls_on:
                enabled_count += 1
                # Check cross-domain communication
                deps = graph.get_dependencies(cid)
                for dep in deps:
                    dep_domain = dep.parameters.get("trust_domain", trust_domain)
                    if isinstance(dep_domain, (int, float)):
                        dep_domain = str(dep_domain)
                    if str(dep_domain) != str(comp_domain):
                        boundary_crossed = True
                        pair = (cid, dep.id)
                        if pair not in cross_domain:
                            cross_domain.append(pair)

            if cert_warning and mtls_on:
                cert_issues.append(
                    f"Certificate rotation interval ({cert_rotation_hours}h) is dangerously "
                    f"short for '{cid}'"
                )

            statuses.append(MTLSStatus(
                component_id=cid,
                mtls_enabled=mtls_on,
                trust_domain=str(comp_domain),
                spiffe_id=spiffe_id,
                cert_rotation_hours=cert_rotation_hours,
                cert_expiry_warning=cert_warning,
                trust_domain_boundary_crossed=boundary_crossed,
            ))

        total = len(graph.components)
        coverage = (enabled_count / total * 100.0) if total > 0 else 0.0

        recommendations: list[str] = []
        if coverage < 100.0:
            not_enabled = [s.component_id for s in statuses if not s.mtls_enabled]
            recommendations.append(
                f"Enable mTLS for {len(not_enabled)} service(s): "
                f"{', '.join(not_enabled[:5])}"
            )
        if cross_domain:
            recommendations.append(
                f"{len(cross_domain)} cross-trust-domain pair(s) detected; "
                "ensure proper trust bundle federation."
            )
        if cert_issues:
            recommendations.append(
                "Increase certificate rotation interval to reduce rotation risk."
            )

        return MTLSReport(
            statuses=statuses,
            overall_mtls_coverage=round(_clamp(coverage), 1),
            trust_domains=sorted(trust_domains),
            cross_domain_pairs=cross_domain,
            cert_rotation_issues=cert_issues,
            recommendations=recommendations,
        )

    # -- retry policy evaluation --------------------------------------------

    def analyze_retry_policies(self, graph: InfraGraph) -> RetryPolicyReport:
        """Evaluate retry policies across the mesh."""
        if not graph.components:
            return RetryPolicyReport(recommendations=["No services to analyze."])

        evaluations: list[RetryPolicyEvaluation] = []
        services_no_budget: list[str] = []
        max_amp = 1.0

        for cid, comp in graph.components.items():
            deps = graph.get_dependencies(cid)
            retry_on = False
            total_retries = 0
            best_budget = 0.0
            backoff = BackoffStrategy.NONE
            init_delay = 0.0
            max_delay = 0.0

            for dep in deps:
                edge = graph.get_dependency_edge(cid, dep.id)
                if edge and edge.retry_strategy.enabled:
                    retry_on = True
                    total_retries = max(total_retries, edge.retry_strategy.max_retries)
                    best_budget = max(best_budget, edge.retry_strategy.retry_budget_per_second)
                    init_delay = max(init_delay, edge.retry_strategy.initial_delay_ms)
                    max_delay = max(max_delay, edge.retry_strategy.max_delay_ms)
                    if edge.retry_strategy.multiplier > 1.0:
                        backoff = BackoffStrategy.EXPONENTIAL
                    elif edge.retry_strategy.multiplier == 1.0 and edge.retry_strategy.enabled:
                        backoff = BackoffStrategy.FIXED if backoff == BackoffStrategy.NONE else backoff

            has_budget = best_budget > 0
            if retry_on and not has_budget:
                services_no_budget.append(cid)

            # Storm risk: no budget + high retry count
            storm_risk = 0.0
            if retry_on and total_retries > 0:
                storm_risk = min(1.0, total_retries / 10.0)
                if has_budget:
                    storm_risk *= 0.2

            # Amplification factor along dependency chains
            if retry_on and total_retries > 0:
                chain_factor = 1.0 + total_retries
                # Multiply along dependency depth
                depth = len(deps)
                if depth > 1:
                    chain_factor = chain_factor ** min(depth, 3)
                max_amp = max(max_amp, chain_factor)

            evaluations.append(RetryPolicyEvaluation(
                component_id=cid,
                retry_enabled=retry_on,
                max_retries=total_retries,
                backoff_strategy=backoff,
                initial_delay_ms=init_delay,
                max_delay_ms=max_delay,
                retry_budget_per_second=best_budget,
                has_budget_limit=has_budget,
                storm_risk=round(_clamp(storm_risk, 0.0, 1.0), 4),
            ))

        overall_storm_risk = 0.0
        if evaluations:
            risks = [e.storm_risk for e in evaluations if e.retry_enabled]
            if risks:
                overall_storm_risk = max(risks)

        recommendations: list[str] = []
        if services_no_budget:
            recommendations.append(
                f"{len(services_no_budget)} service(s) lack retry budgets: "
                f"{', '.join(services_no_budget[:5])}"
            )
        if max_amp > 4.0:
            recommendations.append(
                f"Critical retry amplification factor: {max_amp:.0f}x; "
                "add retry budgets immediately."
            )
        elif max_amp > 2.0:
            recommendations.append(
                f"Retry amplification factor: {max_amp:.0f}x; "
                "consider adding retry budgets."
            )
        no_retry = [e.component_id for e in evaluations if not e.retry_enabled]
        if no_retry and len(no_retry) < len(evaluations):
            recommendations.append(
                f"{len(no_retry)} service(s) have no retry policy configured."
            )

        return RetryPolicyReport(
            evaluations=evaluations,
            retry_storm_risk=round(_clamp(overall_storm_risk, 0.0, 1.0), 4),
            max_amplification_factor=round(max_amp, 2),
            services_without_budget=services_no_budget,
            recommendations=recommendations,
        )

    # -- circuit breaker analysis -------------------------------------------

    def analyze_circuit_breakers(self, graph: InfraGraph) -> CircuitBreakerReport:
        """Analyze circuit breaker configuration per service pair."""
        if not graph.components:
            return CircuitBreakerReport(recommendations=["No services to analyze."])

        pairs: list[CircuitBreakerPairConfig] = []
        misconfigured: list[str] = []
        enabled_count = 0
        total_edges = 0

        for edge in graph.all_dependency_edges():
            total_edges += 1
            cb = edge.circuit_breaker
            effectiveness = 0.0

            if cb.enabled:
                enabled_count += 1
                # Score effectiveness: threshold, recovery timeout, half-open
                effectiveness = 50.0  # base for being enabled
                if 3 <= cb.failure_threshold <= 10:
                    effectiveness += 15.0
                elif cb.failure_threshold > 0:
                    effectiveness += 5.0
                if 10.0 <= cb.recovery_timeout_seconds <= 120.0:
                    effectiveness += 15.0
                elif cb.recovery_timeout_seconds > 0:
                    effectiveness += 5.0
                if cb.half_open_max_requests >= 1:
                    effectiveness += 10.0
                if cb.success_threshold >= 1:
                    effectiveness += 10.0

                # Detect misconfigurations
                if cb.failure_threshold <= 1:
                    misconfigured.append(
                        f"{edge.source_id}->{edge.target_id}: threshold too low ({cb.failure_threshold})"
                    )
                if cb.recovery_timeout_seconds < 5.0 and cb.recovery_timeout_seconds > 0:
                    misconfigured.append(
                        f"{edge.source_id}->{edge.target_id}: recovery timeout too short "
                        f"({cb.recovery_timeout_seconds}s)"
                    )

            pairs.append(CircuitBreakerPairConfig(
                source_id=edge.source_id,
                target_id=edge.target_id,
                enabled=cb.enabled,
                failure_threshold=cb.failure_threshold,
                recovery_timeout_seconds=cb.recovery_timeout_seconds,
                half_open_max_requests=cb.half_open_max_requests,
                success_threshold=cb.success_threshold,
                effectiveness_score=round(_clamp(effectiveness), 1),
            ))

        coverage = (enabled_count / total_edges * 100.0) if total_edges > 0 else 0.0

        recommendations: list[str] = []
        if coverage < 100.0 and total_edges > 0:
            not_enabled = [
                f"{p.source_id}->{p.target_id}" for p in pairs if not p.enabled
            ]
            recommendations.append(
                f"Enable circuit breakers on {len(not_enabled)} edge(s): "
                f"{', '.join(not_enabled[:3])}"
            )
        if misconfigured:
            recommendations.append(
                f"{len(misconfigured)} misconfigured circuit breaker(s) detected."
            )

        return CircuitBreakerReport(
            pairs=pairs,
            coverage_percent=round(_clamp(coverage), 1),
            misconfigured_pairs=misconfigured,
            recommendations=recommendations,
        )

    # -- load balancing analysis --------------------------------------------

    def analyze_load_balancing(self, graph: InfraGraph) -> LoadBalancingReport:
        """Analyze load balancing strategies."""
        if not graph.components:
            return LoadBalancingReport(recommendations=["No services to analyze."])

        analyses: list[LoadBalancingAnalysis] = []
        strategy_dist: dict[str, int] = {}

        for cid, comp in graph.components.items():
            strategy = self._detect_lb_strategy(comp)
            health_check = comp.failover.enabled
            locality = comp.region.region != "" and comp.region.availability_zone != ""

            # Effectiveness scoring
            score = 0.0
            if comp.replicas > 1:
                score += 30.0
            if health_check:
                score += 25.0
            if locality:
                score += 15.0
            if strategy != LoadBalancingStrategy.UNKNOWN:
                score += 20.0
            if strategy == LoadBalancingStrategy.LOCALITY_AWARE:
                score += 10.0
            elif strategy == LoadBalancingStrategy.CONSISTENT_HASHING:
                score += 5.0

            strategy_dist[strategy.value] = strategy_dist.get(strategy.value, 0) + 1

            analyses.append(LoadBalancingAnalysis(
                component_id=cid,
                strategy=strategy,
                replicas=comp.replicas,
                locality_aware=locality,
                sticky_sessions=(strategy == LoadBalancingStrategy.CONSISTENT_HASHING),
                health_check_enabled=health_check,
                effectiveness_score=round(_clamp(score), 1),
            ))

        recommendations: list[str] = []
        single_replica = [a for a in analyses if a.replicas <= 1]
        if single_replica:
            recommendations.append(
                f"{len(single_replica)} service(s) have single replica; "
                "consider adding replicas for load balancing."
            )
        no_hc = [a for a in analyses if not a.health_check_enabled]
        if no_hc:
            recommendations.append(
                f"{len(no_hc)} service(s) lack health checks for load balancing."
            )

        return LoadBalancingReport(
            analyses=analyses,
            strategy_distribution=strategy_dist,
            recommendations=recommendations,
        )

    # -- observability gap detection ----------------------------------------

    def analyze_observability_gaps(self, graph: InfraGraph) -> ObservabilityGapReport:
        """Detect observability gaps: missing metrics, tracing, logging."""
        if not graph.components:
            return ObservabilityGapReport(recommendations=["No services to analyze."])

        gaps: list[ObservabilityGap] = []
        fully = 0
        partial = 0
        uncovered = 0

        for cid, comp in graph.components.items():
            sec = comp.security
            has_metrics = sec.ids_monitored
            has_tracing = sec.encryption_in_transit  # proxy for distributed tracing
            has_logging = sec.log_enabled

            missing: list[ObservabilitySignal] = []
            if not has_metrics:
                missing.append(ObservabilitySignal.METRICS)
            if not has_tracing:
                missing.append(ObservabilitySignal.TRACING)
            if not has_logging:
                missing.append(ObservabilitySignal.LOGGING)

            present = 3 - len(missing)
            cov_score = present / 3.0 * 100.0

            if present == 3:
                fully += 1
            elif present == 0:
                uncovered += 1
            else:
                partial += 1

            gaps.append(ObservabilityGap(
                component_id=cid,
                missing_signals=missing,
                has_metrics=has_metrics,
                has_tracing=has_tracing,
                has_logging=has_logging,
                coverage_score=round(cov_score, 1),
            ))

        total = len(graph.components)
        overall = sum(g.coverage_score for g in gaps) / total if total > 0 else 0.0

        recommendations: list[str] = []
        if uncovered > 0:
            ids = [g.component_id for g in gaps if g.coverage_score == 0.0]
            recommendations.append(
                f"{uncovered} service(s) have no observability: "
                f"{', '.join(ids[:5])}"
            )
        if partial > 0:
            recommendations.append(
                f"{partial} service(s) have incomplete observability coverage."
            )
        # Specific signal gaps
        no_metrics = [g.component_id for g in gaps if not g.has_metrics]
        if no_metrics:
            recommendations.append(
                f"Enable metrics collection for {len(no_metrics)} service(s)."
            )
        no_tracing = [g.component_id for g in gaps if not g.has_tracing]
        if no_tracing:
            recommendations.append(
                f"Enable distributed tracing for {len(no_tracing)} service(s)."
            )

        return ObservabilityGapReport(
            gaps=gaps,
            overall_coverage=round(_clamp(overall), 1),
            fully_covered_count=fully,
            partially_covered_count=partial,
            uncovered_count=uncovered,
            recommendations=recommendations,
        )

    # -- control plane resilience -------------------------------------------

    def analyze_control_plane_resilience(
        self, graph: InfraGraph
    ) -> ControlPlaneResilienceResult:
        """Analyze what happens when the mesh control plane goes down."""
        if not graph.components:
            return ControlPlaneResilienceResult(
                recommendations=["No services to analyze."]
            )

        # Detect control plane components (load balancers or components tagged as control plane)
        cp_components = [
            comp
            for comp in graph.components.values()
            if comp.type == ComponentType.LOAD_BALANCER or "control-plane" in comp.tags
        ]

        is_ha = False
        replicas = 1
        failover = False

        if cp_components:
            total_replicas = sum(c.replicas for c in cp_components)
            replicas = total_replicas
            is_ha = total_replicas >= 3
            failover = any(c.failover.enabled for c in cp_components)
        else:
            # No explicit control plane: assume single instance
            is_ha = False
            replicas = 1

        # Impact estimation
        impact = 0.0
        degraded: list[str] = []

        if not is_ha:
            impact += 30.0
            degraded.append("config_propagation")
        if not failover:
            impact += 20.0
            degraded.append("automatic_failover")

        # cert rotation blocked during outage
        degraded.append("certificate_rotation")

        # SPOFs amplify impact
        spof_count = sum(
            1
            for comp in graph.components.values()
            if comp.replicas <= 1 and not comp.failover.enabled
        )
        impact += min(20.0, spof_count * 5.0)

        # More services = higher impact
        total = len(graph.components)
        if total > 10:
            impact += 10.0
        elif total > 5:
            impact += 5.0

        impact = _clamp(impact)

        recommendations: list[str] = []
        if not is_ha:
            recommendations.append(
                "Deploy control plane with at least 3 replicas for high availability."
            )
        if not failover:
            recommendations.append(
                "Enable automatic failover for control plane components."
            )
        recommendations.append(
            "Ensure data plane proxies cache configuration for control plane outage survival."
        )
        if spof_count > 0:
            recommendations.append(
                f"Eliminate {spof_count} single point(s) of failure in the data plane."
            )

        return ControlPlaneResilienceResult(
            is_highly_available=is_ha,
            replica_count=replicas,
            failover_capable=failover,
            last_known_config_survives=True,
            cert_rotation_blocked=True,
            estimated_impact_percent=round(impact, 1),
            degraded_features=degraded,
            recommendations=recommendations,
        )

    # -- data plane saturation ----------------------------------------------

    def analyze_data_plane_saturation(
        self,
        graph: InfraGraph,
        topology: MeshTopology = MeshTopology.SIDECAR_PROXY,
    ) -> DataPlaneSaturationReport:
        """Analyze sidecar resource limits and connection pool exhaustion."""
        if not graph.components:
            return DataPlaneSaturationReport(
                recommendations=["No services to analyze."]
            )

        mem_overhead, cpu_overhead = _TOPOLOGY_OVERHEAD.get(
            topology, (_SIDECAR_MEMORY_MB, _SIDECAR_CPU_PERCENT)
        )

        results: list[DataPlaneSaturationResult] = []
        saturated = 0
        near_sat = 0
        total_mem = 0.0
        total_cpu = 0.0

        for cid, comp in graph.components.items():
            sidecar_mem = mem_overhead * comp.replicas
            sidecar_cpu = cpu_overhead * comp.replicas
            total_mem += sidecar_mem
            total_cpu += sidecar_cpu

            # Connection pool usage estimation
            conn_usage = 0.0
            if comp.capacity.max_connections > 0:
                conn_usage = (
                    comp.metrics.network_connections
                    / comp.capacity.max_connections
                    * 100.0
                )
            conn_exhausted = conn_usage >= 95.0

            # Saturation score: combination of CPU, memory pressure, connection pool
            sat_score = 0.0
            if comp.metrics.cpu_percent > 0:
                sat_score += min(40.0, comp.metrics.cpu_percent * 0.5)
            if comp.metrics.memory_percent > 0:
                sat_score += min(30.0, comp.metrics.memory_percent * 0.3)
            sat_score += min(30.0, conn_usage * 0.3)

            is_sat = sat_score >= 70.0
            is_near = 50.0 <= sat_score < 70.0

            if is_sat:
                saturated += 1
            elif is_near:
                near_sat += 1

            results.append(DataPlaneSaturationResult(
                component_id=cid,
                sidecar_cpu_percent=round(sidecar_cpu, 2),
                sidecar_memory_mb=round(sidecar_mem, 2),
                connection_pool_usage_percent=round(_clamp(conn_usage), 1),
                connection_pool_exhausted=conn_exhausted,
                is_saturated=is_sat,
                saturation_score=round(_clamp(sat_score), 1),
            ))

        recommendations: list[str] = []
        if saturated > 0:
            sat_ids = [r.component_id for r in results if r.is_saturated]
            recommendations.append(
                f"{saturated} service(s) have saturated data plane: "
                f"{', '.join(sat_ids[:5])}. Increase sidecar resource limits."
            )
        if near_sat > 0:
            recommendations.append(
                f"{near_sat} service(s) are near data plane saturation."
            )
        exhausted = [r for r in results if r.connection_pool_exhausted]
        if exhausted:
            recommendations.append(
                f"{len(exhausted)} service(s) have exhausted connection pools."
            )
        if topology == MeshTopology.SIDECAR_PROXY and total_mem > 1000.0:
            recommendations.append(
                f"Total sidecar memory overhead is {total_mem:.0f}MB; "
                "consider ambient mesh to reduce per-pod overhead."
            )

        return DataPlaneSaturationReport(
            results=results,
            saturated_count=saturated,
            near_saturation_count=near_sat,
            total_sidecar_memory_mb=round(total_mem, 2),
            total_sidecar_cpu_percent=round(total_cpu, 2),
            recommendations=recommendations,
        )

    # -- policy enforcement -------------------------------------------------

    def analyze_policy_enforcement(
        self, graph: InfraGraph
    ) -> PolicyEnforcementReport:
        """Analyze authorization policies and rate limiting at mesh level."""
        if not graph.components:
            return PolicyEnforcementReport(
                recommendations=["No services to analyze."]
            )

        results: list[PolicyEnforcementResult] = []
        strict = 0
        permissive = 0
        disabled = 0

        for cid, comp in graph.components.items():
            sec = comp.security
            # Determine auth policy level
            if sec.auth_required and sec.encryption_in_transit and sec.network_segmented:
                level = PolicyEnforcementLevel.STRICT
                strict += 1
            elif sec.auth_required or sec.network_segmented:
                level = PolicyEnforcementLevel.PERMISSIVE
                permissive += 1
            else:
                level = PolicyEnforcementLevel.DISABLED
                disabled += 1

            rl_enabled = sec.rate_limiting
            rl_rps = float(comp.parameters.get("rate_limit_rps", 0.0))
            net_policy = sec.network_segmented

            # Enforcement score
            score = 0.0
            if level == PolicyEnforcementLevel.STRICT:
                score += 50.0
            elif level == PolicyEnforcementLevel.PERMISSIVE:
                score += 25.0
            if rl_enabled:
                score += 25.0
            if net_policy:
                score += 15.0
            if sec.waf_protected:
                score += 10.0

            results.append(PolicyEnforcementResult(
                component_id=cid,
                auth_policy_level=level,
                rate_limiting_enabled=rl_enabled,
                rate_limit_rps=rl_rps,
                network_policy_applied=net_policy,
                enforcement_score=round(_clamp(score), 1),
            ))

        total = len(graph.components)
        overall = sum(r.enforcement_score for r in results) / total if total > 0 else 0.0

        recommendations: list[str] = []
        if disabled > 0:
            dis_ids = [r.component_id for r in results if r.auth_policy_level == PolicyEnforcementLevel.DISABLED]
            recommendations.append(
                f"{disabled} service(s) have no authorization policy: "
                f"{', '.join(dis_ids[:5])}"
            )
        if permissive > 0:
            recommendations.append(
                f"{permissive} service(s) use permissive enforcement; "
                "consider upgrading to strict."
            )
        no_rl = [r for r in results if not r.rate_limiting_enabled]
        if no_rl:
            recommendations.append(
                f"{len(no_rl)} service(s) lack rate limiting."
            )
        no_net = [r for r in results if not r.network_policy_applied]
        if no_net:
            recommendations.append(
                f"{len(no_net)} service(s) lack network policies."
            )

        return PolicyEnforcementReport(
            results=results,
            strict_count=strict,
            permissive_count=permissive,
            disabled_count=disabled,
            overall_enforcement_score=round(_clamp(overall), 1),
            recommendations=recommendations,
        )

    # -- topology detection -------------------------------------------------

    def detect_topology(
        self,
        graph: InfraGraph,
        default_topology: MeshTopology = MeshTopology.SIDECAR_PROXY,
    ) -> list[MeshTopologyResult]:
        """Detect mesh topology per component."""
        if not graph.components:
            return []

        results: list[MeshTopologyResult] = []
        for cid, comp in graph.components.items():
            topo = MeshTopology(
                comp.parameters.get("mesh_topology", default_topology.value)
            ) if "mesh_topology" in comp.parameters else default_topology

            mem, cpu = _TOPOLOGY_OVERHEAD.get(topo, (0.0, 0.0))

            proxy_type = ""
            if topo == MeshTopology.SIDECAR_PROXY:
                proxy_type = "envoy"
            elif topo == MeshTopology.PER_NODE:
                proxy_type = "linkerd-proxy"
            elif topo == MeshTopology.AMBIENT:
                proxy_type = "ztunnel"

            results.append(MeshTopologyResult(
                component_id=cid,
                topology=topo,
                proxy_type=proxy_type,
                resource_overhead_mb=mem,
                resource_overhead_cpu_percent=cpu,
            ))

        return results

    # -- internal helpers ---------------------------------------------------

    @staticmethod
    def _detect_lb_strategy(comp: Component) -> LoadBalancingStrategy:
        """Detect the load balancing strategy for a component."""
        param_strategy = comp.parameters.get("lb_strategy", "")
        if isinstance(param_strategy, str) and param_strategy:
            try:
                return LoadBalancingStrategy(param_strategy)
            except ValueError:
                pass

        if comp.type == ComponentType.LOAD_BALANCER:
            if comp.region.region and comp.region.availability_zone:
                return LoadBalancingStrategy.LOCALITY_AWARE
            return LoadBalancingStrategy.ROUND_ROBIN

        if comp.replicas > 1:
            return LoadBalancingStrategy.ROUND_ROBIN

        return LoadBalancingStrategy.UNKNOWN
