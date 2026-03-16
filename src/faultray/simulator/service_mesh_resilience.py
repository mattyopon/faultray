"""Service Mesh Resilience Analyzer.

Analyzes resilience patterns within service mesh architectures
(Istio, Linkerd, Consul Connect, App Mesh, Kuma).  Covers mesh
health assessment, sidecar failure simulation, retry storm analysis,
policy conflict detection, control plane outage simulation,
policy recommendation, and mesh overhead calculation.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field

from faultray.model.components import Component, ComponentType
from faultray.model.graph import InfraGraph


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class MeshType(str, Enum):
    """Supported service mesh implementations."""

    ISTIO = "istio"
    LINKERD = "linkerd"
    CONSUL_CONNECT = "consul_connect"
    APP_MESH = "app_mesh"
    KUMA = "kuma"
    CUSTOM = "custom"


class MeshPolicy(str, Enum):
    """Service mesh traffic policies."""

    RETRY = "retry"
    TIMEOUT = "timeout"
    CIRCUIT_BREAKER = "circuit_breaker"
    RATE_LIMIT = "rate_limit"
    OUTLIER_DETECTION = "outlier_detection"
    FAULT_INJECTION = "fault_injection"
    MIRROR = "mirror"


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


class MeshPolicyConfig(BaseModel):
    """Configuration for a single mesh policy."""

    policy: MeshPolicy
    enabled: bool = True
    parameters: dict[str, float | str] = Field(default_factory=dict)
    applied_to: list[str] = Field(default_factory=list)


class MeshHealthReport(BaseModel):
    """Result of a full mesh health assessment."""

    mesh_type: MeshType
    total_services: int = 0
    sidecar_coverage: float = Field(default=0.0, ge=0.0, le=100.0)
    policy_coverage: dict[str, float] = Field(default_factory=dict)
    single_points_of_failure: list[str] = Field(default_factory=list)
    control_plane_resilience: float = Field(default=0.0, ge=0.0, le=100.0)
    data_plane_resilience: float = Field(default=0.0, ge=0.0, le=100.0)
    recommendations: list[str] = Field(default_factory=list)


class SidecarFailureResult(BaseModel):
    """Result of simulating a sidecar proxy failure."""

    affected_service: str = ""
    failure_mode: str = ""
    traffic_impact: str = ""
    fallback_behavior: str = ""
    blast_radius: list[str] = Field(default_factory=list)


class RetryStormAnalysis(BaseModel):
    """Result of analyzing retry storm potential."""

    at_risk_services: list[str] = Field(default_factory=list)
    max_amplification_factor: float = Field(default=1.0, ge=1.0)
    storm_probability: float = Field(default=0.0, ge=0.0, le=1.0)
    affected_paths: list[list[str]] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)


class PolicyConflict(BaseModel):
    """A detected conflict between two mesh policies."""

    policy_a: MeshPolicy
    policy_b: MeshPolicy
    component_id: str = ""
    conflict_type: str = ""
    description: str = ""
    severity: str = "medium"
    resolution: str = ""


class ControlPlaneOutageResult(BaseModel):
    """Result of simulating a control plane outage."""

    mesh_type: MeshType
    affected_features: list[str] = Field(default_factory=list)
    data_plane_continues: bool = True
    config_propagation_blocked: bool = True
    estimated_impact_percent: float = Field(default=0.0, ge=0.0, le=100.0)
    mttr_minutes: float = Field(default=0.0, ge=0.0)
    recommendations: list[str] = Field(default_factory=list)


class MeshOverheadReport(BaseModel):
    """Report of performance overhead introduced by the service mesh."""

    total_latency_overhead_ms: float = Field(default=0.0, ge=0.0)
    per_hop_latency_ms: float = Field(default=0.0, ge=0.0)
    memory_overhead_mb: float = Field(default=0.0, ge=0.0)
    cpu_overhead_percent: float = Field(default=0.0, ge=0.0)
    total_sidecar_instances: int = Field(default=0, ge=0)
    policy_evaluation_ms: float = Field(default=0.0, ge=0.0)
    recommendations: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Base per-hop sidecar latency overhead in ms by mesh type
_MESH_HOP_LATENCY_MS: dict[MeshType, float] = {
    MeshType.ISTIO: 2.5,
    MeshType.LINKERD: 1.5,
    MeshType.CONSUL_CONNECT: 2.0,
    MeshType.APP_MESH: 2.2,
    MeshType.KUMA: 1.8,
    MeshType.CUSTOM: 3.0,
}

# Memory overhead per sidecar in MB by mesh type
_MESH_SIDECAR_MEMORY_MB: dict[MeshType, float] = {
    MeshType.ISTIO: 50.0,
    MeshType.LINKERD: 20.0,
    MeshType.CONSUL_CONNECT: 35.0,
    MeshType.APP_MESH: 40.0,
    MeshType.KUMA: 25.0,
    MeshType.CUSTOM: 30.0,
}

# CPU overhead per sidecar as a percentage
_MESH_SIDECAR_CPU_PERCENT: dict[MeshType, float] = {
    MeshType.ISTIO: 1.5,
    MeshType.LINKERD: 0.8,
    MeshType.CONSUL_CONNECT: 1.2,
    MeshType.APP_MESH: 1.3,
    MeshType.KUMA: 1.0,
    MeshType.CUSTOM: 1.5,
}

# Control plane MTTR in minutes by mesh type
_MESH_CONTROL_PLANE_MTTR: dict[MeshType, float] = {
    MeshType.ISTIO: 10.0,
    MeshType.LINKERD: 5.0,
    MeshType.CONSUL_CONNECT: 8.0,
    MeshType.APP_MESH: 12.0,
    MeshType.KUMA: 7.0,
    MeshType.CUSTOM: 15.0,
}

# Policy evaluation latency in ms per policy type
_POLICY_EVAL_LATENCY_MS: dict[MeshPolicy, float] = {
    MeshPolicy.RETRY: 0.1,
    MeshPolicy.TIMEOUT: 0.05,
    MeshPolicy.CIRCUIT_BREAKER: 0.2,
    MeshPolicy.RATE_LIMIT: 0.15,
    MeshPolicy.OUTLIER_DETECTION: 0.3,
    MeshPolicy.FAULT_INJECTION: 0.1,
    MeshPolicy.MIRROR: 0.5,
}

# Features lost during control plane outage per mesh type
_CONTROL_PLANE_FEATURES: dict[MeshType, list[str]] = {
    MeshType.ISTIO: [
        "certificate_rotation", "policy_updates", "telemetry_configuration",
        "traffic_management_changes", "service_discovery_updates",
    ],
    MeshType.LINKERD: [
        "certificate_rotation", "policy_updates", "service_profiles",
        "traffic_split_updates",
    ],
    MeshType.CONSUL_CONNECT: [
        "intention_updates", "certificate_rotation", "service_discovery",
        "config_entry_updates",
    ],
    MeshType.APP_MESH: [
        "virtual_node_updates", "route_updates", "certificate_management",
        "mesh_configuration",
    ],
    MeshType.KUMA: [
        "policy_updates", "certificate_rotation", "zone_sync",
        "service_discovery",
    ],
    MeshType.CUSTOM: [
        "policy_updates", "certificate_management", "configuration_sync",
    ],
}


def _clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    """Clamp *value* between *lo* and *hi*."""
    return max(lo, min(hi, value))


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class ServiceMeshResilienceEngine:
    """Stateless engine for service mesh resilience analysis."""

    # -- mesh health assessment --------------------------------------------

    def assess_mesh_health(
        self,
        graph: InfraGraph,
        mesh_type: MeshType,
        policies: list[MeshPolicyConfig],
    ) -> MeshHealthReport:
        """Assess the overall health of a service mesh deployment."""
        total_services = len(graph.components)
        if total_services == 0:
            return MeshHealthReport(
                mesh_type=mesh_type,
                total_services=0,
                sidecar_coverage=0.0,
                policy_coverage={},
                single_points_of_failure=[],
                control_plane_resilience=0.0,
                data_plane_resilience=0.0,
                recommendations=["No services found in the mesh"],
            )

        # Sidecar coverage: percentage of services covered by at least one policy
        all_component_ids = set(graph.components.keys())
        covered_ids: set[str] = set()
        for p in policies:
            if p.enabled:
                for cid in p.applied_to:
                    if cid in all_component_ids:
                        covered_ids.add(cid)
        sidecar_coverage = (len(covered_ids) / total_services) * 100.0 if total_services > 0 else 0.0

        # Policy coverage per policy type
        policy_coverage: dict[str, float] = {}
        for mp in MeshPolicy:
            matching = [p for p in policies if p.policy == mp and p.enabled]
            covered_by_policy: set[str] = set()
            for p in matching:
                for cid in p.applied_to:
                    if cid in all_component_ids:
                        covered_by_policy.add(cid)
            policy_coverage[mp.value] = (
                (len(covered_by_policy) / total_services) * 100.0
                if total_services > 0
                else 0.0
            )

        # Single points of failure: single replica with no failover
        spofs: list[str] = []
        for cid, comp in graph.components.items():
            if comp.replicas <= 1 and not comp.failover.enabled:
                dependents = graph.get_dependents(cid)
                if len(dependents) > 0:
                    spofs.append(cid)

        # Control plane resilience: based on mesh type features and coverage
        cp_resilience = 100.0
        if sidecar_coverage < 100.0:
            cp_resilience -= (100.0 - sidecar_coverage) * 0.3
        if len(spofs) > 0:
            cp_resilience -= min(30.0, len(spofs) * 10.0)
        # Bonus for having essential policies
        essential = {MeshPolicy.CIRCUIT_BREAKER, MeshPolicy.RETRY, MeshPolicy.TIMEOUT}
        for ep in essential:
            if policy_coverage.get(ep.value, 0.0) < 50.0:
                cp_resilience -= 10.0
        cp_resilience = _clamp(cp_resilience)

        # Data plane resilience
        dp_resilience = 100.0
        if sidecar_coverage < 100.0:
            dp_resilience -= (100.0 - sidecar_coverage) * 0.4
        if len(spofs) > 0:
            dp_resilience -= min(40.0, len(spofs) * 8.0)
        # Circuit breaker coverage matters for data plane
        cb_coverage = policy_coverage.get(MeshPolicy.CIRCUIT_BREAKER.value, 0.0)
        if cb_coverage < 50.0:
            dp_resilience -= 15.0
        dp_resilience = _clamp(dp_resilience)

        # Recommendations
        recommendations: list[str] = []
        if sidecar_coverage < 100.0:
            uncovered = sorted(all_component_ids - covered_ids)
            recommendations.append(
                f"Extend sidecar coverage to {len(uncovered)} uncovered service(s): "
                f"{', '.join(uncovered[:3])}"
            )
        if spofs:
            recommendations.append(
                f"Eliminate {len(spofs)} single point(s) of failure: {', '.join(spofs[:3])}"
            )
        for ep in essential:
            if policy_coverage.get(ep.value, 0.0) < 50.0:
                recommendations.append(
                    f"Increase {ep.value} policy coverage (currently "
                    f"{policy_coverage.get(ep.value, 0.0):.0f}%)"
                )
        if policy_coverage.get(MeshPolicy.RATE_LIMIT.value, 0.0) < 30.0:
            recommendations.append("Add rate limiting policies to protect services from overload")
        if policy_coverage.get(MeshPolicy.OUTLIER_DETECTION.value, 0.0) < 30.0:
            recommendations.append("Enable outlier detection to automatically remove unhealthy endpoints")

        return MeshHealthReport(
            mesh_type=mesh_type,
            total_services=total_services,
            sidecar_coverage=round(sidecar_coverage, 2),
            policy_coverage={k: round(v, 2) for k, v in policy_coverage.items()},
            single_points_of_failure=spofs,
            control_plane_resilience=round(cp_resilience, 2),
            data_plane_resilience=round(dp_resilience, 2),
            recommendations=recommendations,
        )

    # -- sidecar failure simulation ----------------------------------------

    def simulate_sidecar_failure(
        self,
        graph: InfraGraph,
        component_id: str,
    ) -> SidecarFailureResult:
        """Simulate a sidecar proxy failure for a specific service."""
        comp = graph.get_component(component_id)
        if comp is None:
            return SidecarFailureResult(
                affected_service=component_id,
                failure_mode="unknown",
                traffic_impact="Service not found in graph",
                fallback_behavior="none",
                blast_radius=[],
            )

        # Determine failure mode based on component type
        if comp.type == ComponentType.LOAD_BALANCER:
            failure_mode = "ingress_proxy_down"
            traffic_impact = "All inbound traffic blocked"
            fallback = "direct_connection_if_available"
        elif comp.type == ComponentType.DATABASE:
            failure_mode = "data_plane_proxy_failure"
            traffic_impact = "Database connections disrupted"
            fallback = "direct_database_connection"
        elif comp.type == ComponentType.EXTERNAL_API:
            failure_mode = "egress_proxy_down"
            traffic_impact = "External API calls blocked"
            fallback = "direct_external_connection"
        else:
            failure_mode = "sidecar_crash"
            traffic_impact = "Service-to-service communication disrupted"
            fallback = "application_level_retry"

        # Determine blast radius: all transitively affected components
        affected = graph.get_all_affected(component_id)
        # Also include direct dependencies that lose connectivity
        for dep in graph.get_dependencies(component_id):
            affected.add(dep.id)
        blast_radius = sorted(affected - {component_id})

        # Adjust traffic impact by replicas
        if comp.replicas > 1:
            traffic_impact += f" (mitigated: {comp.replicas} replicas available)"
            fallback = "traffic_redistributed_to_healthy_replicas"

        if comp.failover.enabled:
            fallback = "automatic_failover"

        return SidecarFailureResult(
            affected_service=component_id,
            failure_mode=failure_mode,
            traffic_impact=traffic_impact,
            fallback_behavior=fallback,
            blast_radius=blast_radius,
        )

    # -- retry storm analysis ----------------------------------------------

    def analyze_retry_storms(
        self,
        graph: InfraGraph,
        policies: list[MeshPolicyConfig],
    ) -> RetryStormAnalysis:
        """Analyze the potential for retry storms in the mesh."""
        if not graph.components:
            return RetryStormAnalysis()

        # Build retry config map: component_id -> max_retries
        retry_map: dict[str, int] = {}
        for p in policies:
            if p.policy == MeshPolicy.RETRY and p.enabled:
                max_retries = int(p.parameters.get("max_retries", 3))
                for cid in p.applied_to:
                    if cid in graph.components:
                        retry_map[cid] = max(retry_map.get(cid, 0), max_retries)

        # Also check edge-level retry strategies
        for edge in graph.all_dependency_edges():
            if edge.retry_strategy.enabled:
                cid = edge.source_id
                if cid in graph.components:
                    retry_map[cid] = max(
                        retry_map.get(cid, 0),
                        edge.retry_strategy.max_retries,
                    )

        if not retry_map:
            return RetryStormAnalysis(
                recommendations=["No retry policies configured; consider adding retry policies"],
            )

        # Find paths with retry amplification
        at_risk: set[str] = set()
        affected_paths: list[list[str]] = []
        max_amplification = 1.0

        critical_paths = graph.get_critical_paths(max_paths=50)
        for path in critical_paths:
            if len(path) < 2:
                continue  # single-node paths have no hops to amplify
            # Calculate amplification factor along path
            amplification = 1.0
            path_has_retries = False
            for node_id in path:
                retries = retry_map.get(node_id, 0)
                if retries > 0:
                    amplification *= (1 + retries)
                    path_has_retries = True

            if path_has_retries and amplification > 2.0:
                at_risk.update(path)
                affected_paths.append(path)
                max_amplification = max(max_amplification, amplification)

        # Also check direct edges with multiple retry layers
        for cid in graph.components:
            deps = graph.get_dependencies(cid)
            retries_on_edges = 0
            for dep in deps:
                edge = graph.get_dependency_edge(cid, dep.id)
                if edge and edge.retry_strategy.enabled:
                    retries_on_edges += 1
            if retries_on_edges >= 2 and cid in retry_map:
                at_risk.add(cid)

        # Storm probability: based on retry depth and budget presence
        has_budget = False
        for p in policies:
            if p.policy == MeshPolicy.RETRY and p.enabled:
                if "retry_budget_percent" in p.parameters or "retry_budget_per_second" in p.parameters:
                    has_budget = True
                    break
        for edge in graph.all_dependency_edges():
            if edge.retry_strategy.enabled and edge.retry_strategy.retry_budget_per_second > 0:
                has_budget = True
                break

        storm_probability = 0.0
        if max_amplification > 1.0 and at_risk:
            storm_probability = min(1.0, (max_amplification - 1.0) / 20.0)
            if has_budget:
                storm_probability *= 0.3

        recommendations: list[str] = []
        if max_amplification > 4.0:
            recommendations.append(
                f"Critical retry amplification factor: {max_amplification:.0f}x; "
                "add retry budgets immediately"
            )
        elif max_amplification > 2.0:
            recommendations.append(
                f"Retry amplification factor: {max_amplification:.0f}x; "
                "consider adding retry budgets"
            )
        if not has_budget and retry_map:
            recommendations.append(
                "No retry budget configured; add retry_budget_percent or "
                "retry_budget_per_second to prevent retry storms"
            )
        if len(affected_paths) > 0:
            recommendations.append(
                f"{len(affected_paths)} dependency path(s) at risk of retry amplification"
            )

        return RetryStormAnalysis(
            at_risk_services=sorted(at_risk),
            max_amplification_factor=round(max_amplification, 2),
            storm_probability=round(_clamp(storm_probability, 0.0, 1.0), 4),
            affected_paths=affected_paths,
            recommendations=recommendations,
        )

    # -- policy conflict detection -----------------------------------------

    def detect_policy_conflicts(
        self,
        policies: list[MeshPolicyConfig],
    ) -> list[PolicyConflict]:
        """Detect conflicts between mesh policies."""
        conflicts: list[PolicyConflict] = []

        # Group enabled policies by component
        comp_policies: dict[str, list[MeshPolicyConfig]] = {}
        for p in policies:
            if not p.enabled:
                continue
            for cid in p.applied_to:
                comp_policies.setdefault(cid, []).append(p)

        for cid, cps in comp_policies.items():
            policy_types = {p.policy for p in cps}

            # Conflict 1: Timeout + Retry without coordination
            if MeshPolicy.TIMEOUT in policy_types and MeshPolicy.RETRY in policy_types:
                timeout_p = next(p for p in cps if p.policy == MeshPolicy.TIMEOUT)
                retry_p = next(p for p in cps if p.policy == MeshPolicy.RETRY)
                timeout_val = float(timeout_p.parameters.get("timeout_seconds", 30))
                max_retries = int(retry_p.parameters.get("max_retries", 3))
                retry_delay = float(retry_p.parameters.get("retry_delay_ms", 1000))
                total_retry_time_s = max_retries * retry_delay / 1000.0
                if total_retry_time_s > timeout_val:
                    conflicts.append(PolicyConflict(
                        policy_a=MeshPolicy.TIMEOUT,
                        policy_b=MeshPolicy.RETRY,
                        component_id=cid,
                        conflict_type="timeout_retry_mismatch",
                        description=(
                            f"Total retry time ({total_retry_time_s:.1f}s) exceeds "
                            f"timeout ({timeout_val:.1f}s) on '{cid}'"
                        ),
                        severity="high",
                        resolution="Increase timeout or reduce max_retries/retry_delay",
                    ))

            # Conflict 2: Circuit breaker + Retry without coordination
            if MeshPolicy.CIRCUIT_BREAKER in policy_types and MeshPolicy.RETRY in policy_types:
                cb_p = next(p for p in cps if p.policy == MeshPolicy.CIRCUIT_BREAKER)
                retry_p = next(p for p in cps if p.policy == MeshPolicy.RETRY)
                cb_threshold = int(cb_p.parameters.get("failure_threshold", 5))
                max_retries = int(retry_p.parameters.get("max_retries", 3))
                if max_retries >= cb_threshold:
                    conflicts.append(PolicyConflict(
                        policy_a=MeshPolicy.CIRCUIT_BREAKER,
                        policy_b=MeshPolicy.RETRY,
                        component_id=cid,
                        conflict_type="cb_retry_threshold_conflict",
                        description=(
                            f"Retry count ({max_retries}) >= circuit breaker threshold "
                            f"({cb_threshold}) on '{cid}'; retries will trip the breaker"
                        ),
                        severity="high",
                        resolution="Reduce max_retries below circuit breaker failure_threshold",
                    ))

            # Conflict 3: Rate limit + Fault injection
            if MeshPolicy.RATE_LIMIT in policy_types and MeshPolicy.FAULT_INJECTION in policy_types:
                conflicts.append(PolicyConflict(
                    policy_a=MeshPolicy.RATE_LIMIT,
                    policy_b=MeshPolicy.FAULT_INJECTION,
                    component_id=cid,
                    conflict_type="rate_limit_fault_injection_overlap",
                    description=(
                        f"Rate limiting and fault injection both active on '{cid}'; "
                        "fault injection may trigger rate limits unexpectedly"
                    ),
                    severity="medium",
                    resolution="Exclude fault-injected traffic from rate limit counters",
                ))

            # Conflict 4: Mirror + Rate limit
            if MeshPolicy.MIRROR in policy_types and MeshPolicy.RATE_LIMIT in policy_types:
                conflicts.append(PolicyConflict(
                    policy_a=MeshPolicy.MIRROR,
                    policy_b=MeshPolicy.RATE_LIMIT,
                    component_id=cid,
                    conflict_type="mirror_rate_limit_amplification",
                    description=(
                        f"Traffic mirroring doubles request volume on '{cid}'; "
                        "rate limits may not account for mirrored traffic"
                    ),
                    severity="medium",
                    resolution="Adjust rate limits to account for mirrored traffic volume",
                ))

            # Conflict 5: Outlier detection + Circuit breaker with mismatched thresholds
            if MeshPolicy.OUTLIER_DETECTION in policy_types and MeshPolicy.CIRCUIT_BREAKER in policy_types:
                od_p = next(p for p in cps if p.policy == MeshPolicy.OUTLIER_DETECTION)
                cb_p = next(p for p in cps if p.policy == MeshPolicy.CIRCUIT_BREAKER)
                od_interval = float(od_p.parameters.get("interval_seconds", 10))
                cb_recovery = float(cb_p.parameters.get("recovery_timeout_seconds", 60))
                if od_interval > cb_recovery:
                    conflicts.append(PolicyConflict(
                        policy_a=MeshPolicy.OUTLIER_DETECTION,
                        policy_b=MeshPolicy.CIRCUIT_BREAKER,
                        component_id=cid,
                        conflict_type="outlier_cb_timing_conflict",
                        description=(
                            f"Outlier detection interval ({od_interval:.0f}s) exceeds "
                            f"circuit breaker recovery timeout ({cb_recovery:.0f}s) on '{cid}'"
                        ),
                        severity="low",
                        resolution="Reduce outlier detection interval below CB recovery timeout",
                    ))

        return conflicts

    # -- control plane outage simulation -----------------------------------

    def simulate_control_plane_outage(
        self,
        graph: InfraGraph,
        mesh_type: MeshType,
    ) -> ControlPlaneOutageResult:
        """Simulate a complete control plane outage for the mesh."""
        total_services = len(graph.components)
        features = _CONTROL_PLANE_FEATURES.get(mesh_type, [])
        mttr = _MESH_CONTROL_PLANE_MTTR.get(mesh_type, 15.0)

        # Data plane continues with last-known configuration
        data_plane_continues = True
        config_propagation_blocked = True

        # Impact estimation: based on how many services would be affected
        # by inability to update configs / rotate certs
        if total_services == 0:
            impact_percent = 0.0
        else:
            # Base impact from losing config updates
            impact_percent = 20.0
            # Higher impact for meshes with more features at risk
            impact_percent += len(features) * 3.0
            # More services = slower cert rotation = higher risk
            if total_services > 10:
                impact_percent += 10.0
            elif total_services > 5:
                impact_percent += 5.0
            # SPOFs amplify impact
            spof_count = sum(
                1 for comp in graph.components.values()
                if comp.replicas <= 1 and not comp.failover.enabled
            )
            impact_percent += min(20.0, spof_count * 5.0)

        impact_percent = _clamp(impact_percent)

        recommendations: list[str] = []
        recommendations.append(
            f"Deploy {mesh_type.value} control plane with high availability (multi-replica)"
        )
        if "certificate_rotation" in features:
            recommendations.append(
                "Ensure certificates have sufficient validity period to survive outage"
            )
        if total_services > 5:
            recommendations.append(
                "Implement control plane health monitoring with automatic failover"
            )
        recommendations.append(
            "Pre-cache service discovery data on data plane proxies"
        )
        if mttr > 10.0:
            recommendations.append(
                f"Reduce MTTR from {mttr:.0f} minutes by automating control plane recovery"
            )

        return ControlPlaneOutageResult(
            mesh_type=mesh_type,
            affected_features=features,
            data_plane_continues=data_plane_continues,
            config_propagation_blocked=config_propagation_blocked,
            estimated_impact_percent=round(impact_percent, 2),
            mttr_minutes=mttr,
            recommendations=recommendations,
        )

    # -- policy recommendation ---------------------------------------------

    def recommend_mesh_policies(
        self,
        graph: InfraGraph,
    ) -> list[MeshPolicyConfig]:
        """Recommend mesh policies based on the infrastructure graph."""
        recommendations: list[MeshPolicyConfig] = []
        if not graph.components:
            return recommendations

        all_ids = list(graph.components.keys())

        # 1. Retry policy for all services
        recommendations.append(MeshPolicyConfig(
            policy=MeshPolicy.RETRY,
            enabled=True,
            parameters={"max_retries": 3.0, "retry_delay_ms": 100.0},
            applied_to=all_ids,
        ))

        # 2. Timeout policy for all services
        recommendations.append(MeshPolicyConfig(
            policy=MeshPolicy.TIMEOUT,
            enabled=True,
            parameters={"timeout_seconds": 30.0},
            applied_to=all_ids,
        ))

        # 3. Circuit breaker for services with dependents
        cb_targets: list[str] = []
        for cid in all_ids:
            dependents = graph.get_dependents(cid)
            if len(dependents) > 0:
                cb_targets.append(cid)
        if cb_targets:
            recommendations.append(MeshPolicyConfig(
                policy=MeshPolicy.CIRCUIT_BREAKER,
                enabled=True,
                parameters={"failure_threshold": 5.0, "recovery_timeout_seconds": 60.0},
                applied_to=cb_targets,
            ))

        # 4. Rate limiting for entry points (no dependents) and external APIs
        rate_limit_targets: list[str] = []
        for cid, comp in graph.components.items():
            dependents = graph.get_dependents(cid)
            if len(dependents) == 0 or comp.type == ComponentType.EXTERNAL_API:
                rate_limit_targets.append(cid)
        if rate_limit_targets:
            recommendations.append(MeshPolicyConfig(
                policy=MeshPolicy.RATE_LIMIT,
                enabled=True,
                parameters={"requests_per_second": 1000.0},
                applied_to=rate_limit_targets,
            ))

        # 5. Outlier detection for services with replicas
        od_targets: list[str] = []
        for cid, comp in graph.components.items():
            if comp.replicas > 1:
                od_targets.append(cid)
        if od_targets:
            recommendations.append(MeshPolicyConfig(
                policy=MeshPolicy.OUTLIER_DETECTION,
                enabled=True,
                parameters={"interval_seconds": 10.0, "consecutive_errors": 5.0},
                applied_to=od_targets,
            ))

        return recommendations

    # -- mesh overhead calculation -----------------------------------------

    def calculate_mesh_overhead(
        self,
        graph: InfraGraph,
        policies: list[MeshPolicyConfig],
        mesh_type: MeshType = MeshType.ISTIO,
    ) -> MeshOverheadReport:
        """Calculate performance overhead of the service mesh."""
        total_services = len(graph.components)
        if total_services == 0:
            return MeshOverheadReport(
                recommendations=["No services to measure overhead for"],
            )

        hop_latency = _MESH_HOP_LATENCY_MS.get(mesh_type, 3.0)
        sidecar_mem = _MESH_SIDECAR_MEMORY_MB.get(mesh_type, 30.0)
        sidecar_cpu = _MESH_SIDECAR_CPU_PERCENT.get(mesh_type, 1.5)

        # Total sidecar instances = sum of replicas across all services
        total_sidecars = sum(comp.replicas for comp in graph.components.values())

        # Calculate total policy evaluation latency
        policy_eval_ms = 0.0
        for p in policies:
            if p.enabled:
                policy_eval_ms += _POLICY_EVAL_LATENCY_MS.get(p.policy, 0.1)

        # Find longest dependency path for worst-case latency
        critical_paths = graph.get_critical_paths(max_paths=10)
        max_hops = 0
        if critical_paths:
            max_hops = max(len(path) - 1 for path in critical_paths) if critical_paths else 0

        # Each hop adds sidecar latency (inbound + outbound = 2x per hop)
        per_hop_total = hop_latency * 2 + policy_eval_ms
        total_latency = per_hop_total * max_hops if max_hops > 0 else per_hop_total

        # Memory and CPU overhead
        total_memory = sidecar_mem * total_sidecars
        total_cpu = sidecar_cpu * total_sidecars

        recommendations: list[str] = []
        if total_latency > 20.0:
            recommendations.append(
                f"High mesh latency overhead ({total_latency:.1f}ms); "
                "consider reducing dependency chain depth"
            )
        if total_memory > 1000.0:
            recommendations.append(
                f"High sidecar memory usage ({total_memory:.0f}MB total); "
                "consider using a lighter mesh like Linkerd"
            )
        if total_cpu > 10.0:
            recommendations.append(
                f"Significant CPU overhead ({total_cpu:.1f}%); "
                "review sidecar resource limits"
            )
        if policy_eval_ms > 1.0:
            recommendations.append(
                f"Policy evaluation overhead ({policy_eval_ms:.2f}ms per request); "
                "consolidate or simplify policies"
            )
        if total_sidecars > 50:
            recommendations.append(
                f"{total_sidecars} sidecar instances; consider ambient mesh mode "
                "to reduce per-pod overhead"
            )

        return MeshOverheadReport(
            total_latency_overhead_ms=round(total_latency, 2),
            per_hop_latency_ms=round(per_hop_total, 2),
            memory_overhead_mb=round(total_memory, 2),
            cpu_overhead_percent=round(total_cpu, 2),
            total_sidecar_instances=total_sidecars,
            policy_evaluation_ms=round(policy_eval_ms, 2),
            recommendations=recommendations,
        )
