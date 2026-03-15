"""Risk Heat Map Engine.

Generates a multi-dimensional risk heat map of infrastructure components.
Each component is scored across multiple risk dimensions, creating a
comprehensive view of where risk concentrates in the system.

Dimensions:
- Blast Radius: How many components are affected if this fails
- SPOF Risk: Single point of failure exposure
- Utilization Risk: How close to capacity limits
- Dependency Risk: How deep in the dependency chain
- Recovery Risk: How hard to recover from failure
- Security Risk: Security posture score
- Change Risk: How frequently this component changes
- External Dependency: Reliance on external services
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from infrasim.model.components import ComponentType
from infrasim.model.graph import InfraGraph


class RiskDimension(str, Enum):
    """Risk scoring dimensions for heat map analysis."""

    BLAST_RADIUS = "blast_radius"
    SPOF = "spof"
    UTILIZATION = "utilization"
    DEPENDENCY_DEPTH = "dependency_depth"
    RECOVERY = "recovery"
    SECURITY = "security"
    CHANGE_FREQUENCY = "change_frequency"
    EXTERNAL_DEPENDENCY = "external_dependency"


# Default weights for each risk dimension (must sum to 1.0)
DEFAULT_WEIGHTS: dict[RiskDimension, float] = {
    RiskDimension.BLAST_RADIUS: 0.20,
    RiskDimension.SPOF: 0.20,
    RiskDimension.UTILIZATION: 0.15,
    RiskDimension.DEPENDENCY_DEPTH: 0.10,
    RiskDimension.RECOVERY: 0.15,
    RiskDimension.SECURITY: 0.10,
    RiskDimension.CHANGE_FREQUENCY: 0.05,
    RiskDimension.EXTERNAL_DEPENDENCY: 0.05,
}


def _risk_color(score: float) -> str:
    """Map a 0-1 risk score to a hex color.

    0.0-0.25: #28a745 (green)
    0.25-0.5: #ffc107 (yellow)
    0.5-0.75: #fd7e14 (orange)
    0.75-1.0: #dc3545 (red)
    """
    if score < 0.25:
        return "#28a745"
    elif score < 0.5:
        return "#ffc107"
    elif score < 0.75:
        return "#fd7e14"
    else:
        return "#dc3545"


def _risk_level(score: float) -> str:
    """Map a 0-1 risk score to a human-readable level."""
    if score < 0.25:
        return "low"
    elif score < 0.5:
        return "medium"
    elif score < 0.75:
        return "high"
    else:
        return "critical"


@dataclass
class ComponentRiskProfile:
    """Risk profile for a single infrastructure component."""

    component_id: str
    component_name: str
    component_type: str
    risk_scores: dict[RiskDimension, float] = field(default_factory=dict)
    overall_risk: float = 0.0
    risk_level: str = "low"
    risk_factors: list[str] = field(default_factory=list)
    color: str = "#28a745"

    def to_dict(self) -> dict:
        return {
            "component_id": self.component_id,
            "component_name": self.component_name,
            "component_type": self.component_type,
            "risk_scores": {k.value: round(v, 3) for k, v in self.risk_scores.items()},
            "overall_risk": round(self.overall_risk, 3),
            "risk_level": self.risk_level,
            "risk_factors": self.risk_factors,
            "color": self.color,
        }


@dataclass
class RiskZone:
    """A logical grouping of components by type/layer."""

    name: str
    components: list[ComponentRiskProfile] = field(default_factory=list)
    zone_risk: float = 0.0
    description: str = ""

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "components": [c.to_dict() for c in self.components],
            "zone_risk": round(self.zone_risk, 3),
            "description": self.description,
        }


@dataclass
class HeatMapData:
    """Complete heat map analysis result."""

    components: list[ComponentRiskProfile] = field(default_factory=list)
    zones: list[RiskZone] = field(default_factory=list)
    hotspots: list[ComponentRiskProfile] = field(default_factory=list)
    overall_risk_score: float = 0.0
    risk_distribution: dict[str, int] = field(default_factory=dict)
    dimension_weights: dict[RiskDimension, float] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "components": [c.to_dict() for c in self.components],
            "zones": [z.to_dict() for z in self.zones],
            "hotspots": [c.to_dict() for c in self.hotspots],
            "overall_risk_score": round(self.overall_risk_score, 3),
            "risk_distribution": self.risk_distribution,
            "dimension_weights": {k.value: round(v, 3) for k, v in self.dimension_weights.items()},
        }


# ---- Zone name mapping ----
_ZONE_MAP: dict[ComponentType, tuple[str, str]] = {
    ComponentType.LOAD_BALANCER: ("Network Layer", "Load balancers and traffic routing"),
    ComponentType.WEB_SERVER: ("Web Layer", "Web servers and frontend proxies"),
    ComponentType.APP_SERVER: ("Application Layer", "Application servers and business logic"),
    ComponentType.DATABASE: ("Database Layer", "Databases and persistent storage"),
    ComponentType.CACHE: ("Cache Layer", "Caching systems for performance"),
    ComponentType.QUEUE: ("Message Queue Layer", "Asynchronous message processing"),
    ComponentType.STORAGE: ("Storage Layer", "File and object storage"),
    ComponentType.DNS: ("DNS Layer", "DNS resolution and service discovery"),
    ComponentType.EXTERNAL_API: ("External APIs", "Third-party API dependencies"),
    ComponentType.CUSTOM: ("Custom Components", "Custom infrastructure components"),
}


class RiskHeatMapEngine:
    """Analyzes infrastructure graphs to produce multi-dimensional risk heat maps."""

    def __init__(
        self,
        weights: dict[RiskDimension, float] | None = None,
    ) -> None:
        self.weights = weights or dict(DEFAULT_WEIGHTS)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def analyze(self, graph: InfraGraph) -> HeatMapData:
        """Perform full heat map analysis on an infrastructure graph."""
        profiles = [
            self.get_component_risk(graph, comp_id)
            for comp_id in graph.components
        ]

        # Sort by overall risk descending
        profiles.sort(key=lambda p: p.overall_risk, reverse=True)

        zones = self.group_by_zones(graph)
        hotspots = profiles[:5] if profiles else []

        # Overall risk = weighted average of all component risks
        if profiles:
            overall = sum(p.overall_risk for p in profiles) / len(profiles)
        else:
            overall = 0.0

        # Risk distribution
        distribution: dict[str, int] = {"critical": 0, "high": 0, "medium": 0, "low": 0}
        for p in profiles:
            distribution[p.risk_level] = distribution.get(p.risk_level, 0) + 1

        return HeatMapData(
            components=profiles,
            zones=zones,
            hotspots=hotspots,
            overall_risk_score=overall,
            risk_distribution=distribution,
            dimension_weights=dict(self.weights),
        )

    def get_component_risk(self, graph: InfraGraph, component_id: str) -> ComponentRiskProfile:
        """Calculate the risk profile for a single component."""
        comp = graph.get_component(component_id)
        if comp is None:
            return ComponentRiskProfile(
                component_id=component_id,
                component_name="unknown",
                component_type="unknown",
            )

        total_components = len(graph.components)
        risk_scores: dict[RiskDimension, float] = {}
        factors: list[str] = []

        # ---- Blast Radius ----
        affected = graph.get_all_affected(component_id)
        if total_components > 1:
            blast = len(affected) / (total_components - 1)
        else:
            blast = 0.0
        blast = min(1.0, blast)
        risk_scores[RiskDimension.BLAST_RADIUS] = blast
        if blast > 0.5:
            factors.append(
                f"High blast radius: failure affects {len(affected)} of "
                f"{total_components - 1} other components ({blast * 100:.0f}%)"
            )

        # ---- SPOF Risk ----
        dependents = graph.get_dependents(component_id)
        if comp.replicas <= 1 and len(dependents) > 0:
            spof = 1.0
            factors.append(
                f"Single point of failure: {len(dependents)} component(s) depend on "
                f"this with only {comp.replicas} replica(s)"
            )
        else:
            spof = 0.0
        risk_scores[RiskDimension.SPOF] = spof

        # ---- Utilization Risk ----
        util = comp.utilization()
        util_risk = min(1.0, util / 100.0)
        risk_scores[RiskDimension.UTILIZATION] = util_risk
        if util_risk > 0.7:
            factors.append(f"High utilization: {util:.0f}% of capacity")

        # ---- Dependency Depth ----
        max_depth_graph = self._max_graph_depth(graph)
        depth_to_node = self._depth_to_node(graph, component_id)
        if max_depth_graph > 0:
            depth_risk = depth_to_node / max_depth_graph
        else:
            depth_risk = 0.0
        depth_risk = min(1.0, depth_risk)
        risk_scores[RiskDimension.DEPENDENCY_DEPTH] = depth_risk
        if depth_risk > 0.5:
            factors.append(
                f"Deep in dependency chain: depth {depth_to_node} of max {max_depth_graph}"
            )

        # ---- Recovery Risk ----
        has_failover = 1.0 if comp.failover.enabled else 0.0
        has_autoscaling = 1.0 if comp.autoscaling.enabled else 0.0
        has_health_check = 1.0 if comp.failover.health_check_interval_seconds > 0 else 0.0
        has_replicas = 1.0 if comp.replicas > 1 else 0.0
        recovery_risk = 1.0 - (
            has_failover * 0.3
            + has_autoscaling * 0.3
            + has_health_check * 0.2
            + has_replicas * 0.2
        )
        recovery_risk = max(0.0, min(1.0, recovery_risk))
        risk_scores[RiskDimension.RECOVERY] = recovery_risk
        if recovery_risk > 0.7:
            missing = []
            if not comp.failover.enabled:
                missing.append("failover")
            if not comp.autoscaling.enabled:
                missing.append("autoscaling")
            if comp.replicas <= 1:
                missing.append("replicas > 1")
            factors.append(f"Limited recovery options: missing {', '.join(missing)}")

        # ---- Security Risk ----
        has_cb = self._has_circuit_breaker(graph, component_id)
        has_rate_limiting = 1.0 if comp.security.rate_limiting else 0.0
        is_internal = 0.0 if comp.type == ComponentType.EXTERNAL_API else 1.0
        security_risk = 1.0 - (
            has_cb * 0.4
            + has_rate_limiting * 0.3
            + is_internal * 0.3
        )
        security_risk = max(0.0, min(1.0, security_risk))
        risk_scores[RiskDimension.SECURITY] = security_risk
        if security_risk > 0.5:
            issues = []
            if not has_cb:
                issues.append("no circuit breaker")
            if not comp.security.rate_limiting:
                issues.append("no rate limiting")
            if comp.type == ComponentType.EXTERNAL_API:
                issues.append("external dependency")
            factors.append(f"Security concerns: {', '.join(issues)}")

        # ---- Change Frequency ----
        # Approximated by deployment downtime and maintenance windows
        deploy_risk = min(1.0, comp.operational_profile.deploy_downtime_seconds / 300.0)
        risk_scores[RiskDimension.CHANGE_FREQUENCY] = deploy_risk

        # ---- External Dependency ----
        ext_risk = 1.0 if comp.type == ComponentType.EXTERNAL_API else 0.0
        if comp.external_sla is not None:
            # Lower SLA = higher risk
            ext_risk = max(ext_risk, 1.0 - (comp.external_sla.provider_sla / 100.0))
        risk_scores[RiskDimension.EXTERNAL_DEPENDENCY] = min(1.0, ext_risk)
        if ext_risk > 0.5:
            factors.append("External dependency with limited control")

        # ---- Overall weighted score ----
        overall = sum(
            risk_scores.get(dim, 0.0) * self.weights.get(dim, 0.0)
            for dim in RiskDimension
        )
        overall = max(0.0, min(1.0, overall))

        level = _risk_level(overall)
        color = _risk_color(overall)

        return ComponentRiskProfile(
            component_id=component_id,
            component_name=comp.name,
            component_type=comp.type.value,
            risk_scores=risk_scores,
            overall_risk=overall,
            risk_level=level,
            risk_factors=factors,
            color=color,
        )

    def identify_hotspots(
        self, graph: InfraGraph, top_n: int = 5
    ) -> list[ComponentRiskProfile]:
        """Return the top N riskiest components."""
        profiles = [
            self.get_component_risk(graph, cid) for cid in graph.components
        ]
        profiles.sort(key=lambda p: p.overall_risk, reverse=True)
        return profiles[:top_n]

    def group_by_zones(self, graph: InfraGraph) -> list[RiskZone]:
        """Group components into risk zones based on component type."""
        zone_map: dict[str, RiskZone] = {}

        for comp_id, comp in graph.components.items():
            zone_name, zone_desc = _ZONE_MAP.get(
                comp.type, ("Custom Components", "Custom infrastructure components")
            )
            if zone_name not in zone_map:
                zone_map[zone_name] = RiskZone(
                    name=zone_name,
                    description=zone_desc,
                )
            profile = self.get_component_risk(graph, comp_id)
            zone_map[zone_name].components.append(profile)

        # Calculate zone-level risk as average of component risks
        zones = list(zone_map.values())
        for zone in zones:
            if zone.components:
                zone.zone_risk = sum(c.overall_risk for c in zone.components) / len(
                    zone.components
                )
        zones.sort(key=lambda z: z.zone_risk, reverse=True)
        return zones

    def to_matrix(self, data: HeatMapData) -> list[list[float]]:
        """Convert heat map data to a 2D matrix for grid visualization.

        Rows = components, Columns = risk dimensions.
        """
        dimensions = list(RiskDimension)
        matrix: list[list[float]] = []
        for profile in data.components:
            row = [
                round(profile.risk_scores.get(dim, 0.0), 3) for dim in dimensions
            ]
            matrix.append(row)
        return matrix

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _max_graph_depth(self, graph: InfraGraph) -> int:
        """Calculate the maximum depth of the dependency graph."""
        max_depth = 0
        for comp_id in graph.components:
            depth = self._depth_to_node(graph, comp_id)
            if depth > max_depth:
                max_depth = depth
        return max_depth

    def _depth_to_node(self, graph: InfraGraph, component_id: str) -> int:
        """Calculate the longest path from any root to this node."""
        # BFS backwards through dependencies to find max depth
        visited: set[str] = set()
        max_depth = 0

        def _dfs(cid: str, depth: int) -> None:
            nonlocal max_depth
            if cid in visited:
                return
            visited.add(cid)
            if depth > max_depth:
                max_depth = depth
            for dep in graph.get_dependencies(cid):
                _dfs(dep.id, depth + 1)
            visited.discard(cid)

        _dfs(component_id, 0)
        return max_depth

    def _has_circuit_breaker(self, graph: InfraGraph, component_id: str) -> float:
        """Check if any edge to/from this component has a circuit breaker."""
        # Check outgoing edges
        dependencies = graph.get_dependencies(component_id)
        for dep in dependencies:
            edge = graph.get_dependency_edge(component_id, dep.id)
            if edge and edge.circuit_breaker.enabled:
                return 1.0
        # Check incoming edges
        dependents = graph.get_dependents(component_id)
        for dep in dependents:
            edge = graph.get_dependency_edge(dep.id, component_id)
            if edge and edge.circuit_breaker.enabled:
                return 1.0
        return 0.0
