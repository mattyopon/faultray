"""Resource optimizer — right-sizing and cost optimization recommendations.

Analyzes infrastructure components to identify over-provisioned,
under-provisioned, and idle resources, then generates optimization
recommendations with estimated cost savings.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from faultray.model.components import ComponentType
from faultray.model.graph import InfraGraph


class OptimizationType(str, Enum):
    """Type of optimization recommendation."""

    SCALE_DOWN = "scale_down"
    SCALE_UP = "scale_up"
    RIGHT_SIZE = "right_size"
    CONSOLIDATE = "consolidate"
    DECOMMISSION = "decommission"
    ADD_AUTOSCALING = "add_autoscaling"
    ENABLE_SPOT = "enable_spot"
    TIERED_STORAGE = "tiered_storage"


class Priority(str, Enum):
    """Priority of a recommendation."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass
class ResourceUsage:
    """Resource usage profile for a component."""

    component_id: str
    component_name: str
    component_type: str
    replicas: int
    utilization_percent: float
    is_over_provisioned: bool
    is_under_provisioned: bool
    is_idle: bool
    has_autoscaling: bool
    estimated_monthly_cost: float


@dataclass
class Recommendation:
    """A single optimization recommendation."""

    optimization_type: OptimizationType
    priority: Priority
    component_id: str
    component_name: str
    description: str
    current_state: str
    recommended_state: str
    estimated_monthly_savings: float
    risk_level: str  # "low", "medium", "high"
    implementation_effort: str  # "trivial", "easy", "moderate", "complex"


@dataclass
class OptimizationReport:
    """Full resource optimization report."""

    resource_usages: list[ResourceUsage]
    recommendations: list[Recommendation]
    total_monthly_cost: float
    potential_monthly_savings: float
    savings_percent: float
    over_provisioned_count: int
    under_provisioned_count: int
    idle_count: int
    optimization_score: float  # 0-100 (100 = perfectly optimized)


# Default cost estimates per component type per replica per month
_DEFAULT_COSTS = {
    ComponentType.WEB_SERVER: 50.0,
    ComponentType.APP_SERVER: 100.0,
    ComponentType.DATABASE: 200.0,
    ComponentType.CACHE: 80.0,
    ComponentType.QUEUE: 60.0,
    ComponentType.LOAD_BALANCER: 30.0,
    ComponentType.DNS: 10.0,
    ComponentType.STORAGE: 40.0,
    ComponentType.EXTERNAL_API: 0.0,
    ComponentType.CUSTOM: 50.0,
}


class ResourceOptimizer:
    """Analyze and optimize infrastructure resource allocation."""

    def __init__(
        self,
        over_threshold: float = 30.0,
        under_threshold: float = 80.0,
        idle_threshold: float = 5.0,
    ) -> None:
        self._over_threshold = over_threshold
        self._under_threshold = under_threshold
        self._idle_threshold = idle_threshold

    def analyze(self, graph: InfraGraph) -> OptimizationReport:
        """Analyze infrastructure and generate optimization report."""
        if not graph.components:
            return OptimizationReport(
                resource_usages=[],
                recommendations=[],
                total_monthly_cost=0,
                potential_monthly_savings=0,
                savings_percent=0,
                over_provisioned_count=0,
                under_provisioned_count=0,
                idle_count=0,
                optimization_score=100.0,
            )

        usages = self._analyze_usage(graph)
        recommendations = self._generate_recommendations(graph, usages)

        total_cost = sum(u.estimated_monthly_cost for u in usages)
        total_savings = sum(r.estimated_monthly_savings for r in recommendations)
        savings_pct = (total_savings / total_cost * 100) if total_cost > 0 else 0

        over = sum(1 for u in usages if u.is_over_provisioned)
        under = sum(1 for u in usages if u.is_under_provisioned)
        idle = sum(1 for u in usages if u.is_idle)

        # Optimization score: 100 minus penalties
        total = len(usages)
        penalty = (over + under + idle) / total * 50 if total > 0 else 0
        opt_score = max(0, 100 - penalty)

        recommendations.sort(
            key=lambda r: r.estimated_monthly_savings, reverse=True
        )

        return OptimizationReport(
            resource_usages=usages,
            recommendations=recommendations,
            total_monthly_cost=round(total_cost, 2),
            potential_monthly_savings=round(total_savings, 2),
            savings_percent=round(savings_pct, 1),
            over_provisioned_count=over,
            under_provisioned_count=under,
            idle_count=idle,
            optimization_score=round(opt_score, 1),
        )

    def get_usage(self, graph: InfraGraph, component_id: str) -> ResourceUsage | None:
        """Get resource usage for a specific component."""
        comp = graph.get_component(component_id)
        if comp is None:
            return None
        return self._build_usage(comp)

    def _analyze_usage(self, graph: InfraGraph) -> list[ResourceUsage]:
        """Analyze resource usage for all components."""
        usages: list[ResourceUsage] = []
        for comp in graph.components.values():
            usages.append(self._build_usage(comp))
        return usages

    def _build_usage(self, comp) -> ResourceUsage:
        """Build usage profile for a single component."""
        util = comp.utilization()
        cost_per_replica = _DEFAULT_COSTS.get(comp.type, 50.0)
        if comp.cost_profile.hourly_infra_cost > 0:
            cost_per_replica = comp.cost_profile.hourly_infra_cost * 720  # 30 days

        monthly_cost = cost_per_replica * comp.replicas

        return ResourceUsage(
            component_id=comp.id,
            component_name=comp.name,
            component_type=comp.type.value,
            replicas=comp.replicas,
            utilization_percent=round(util, 1),
            is_over_provisioned=util < self._over_threshold and comp.replicas > 1,
            is_under_provisioned=util > self._under_threshold,
            is_idle=util < self._idle_threshold,
            has_autoscaling=comp.autoscaling.enabled,
            estimated_monthly_cost=round(monthly_cost, 2),
        )

    def _generate_recommendations(
        self,
        graph: InfraGraph,
        usages: list[ResourceUsage],
    ) -> list[Recommendation]:
        """Generate optimization recommendations."""
        recs: list[Recommendation] = []

        for usage in usages:
            comp = graph.get_component(usage.component_id)
            if comp is None:
                continue

            # Idle resources → decommission or consolidate
            if usage.is_idle and comp.replicas > 0:
                dependents = graph.get_dependents(comp.id)
                if not dependents:
                    recs.append(Recommendation(
                        optimization_type=OptimizationType.DECOMMISSION,
                        priority=Priority.MEDIUM,
                        component_id=comp.id,
                        component_name=comp.name,
                        description=f"{comp.name} is idle ({usage.utilization_percent}% util) with no dependents",
                        current_state=f"{comp.replicas} replicas, {usage.utilization_percent}% util",
                        recommended_state="Decommission or archive",
                        estimated_monthly_savings=usage.estimated_monthly_cost,
                        risk_level="low",
                        implementation_effort="easy",
                    ))
                else:
                    recs.append(Recommendation(
                        optimization_type=OptimizationType.SCALE_DOWN,
                        priority=Priority.LOW,
                        component_id=comp.id,
                        component_name=comp.name,
                        description=f"{comp.name} is idle but has {len(dependents)} dependent(s)",
                        current_state=f"{comp.replicas} replicas, {usage.utilization_percent}% util",
                        recommended_state="Reduce to 1 replica",
                        estimated_monthly_savings=usage.estimated_monthly_cost * 0.5,
                        risk_level="medium",
                        implementation_effort="easy",
                    ))

            # Over-provisioned → scale down
            elif usage.is_over_provisioned:
                target_replicas = max(1, comp.replicas // 2)
                savings = (comp.replicas - target_replicas) / comp.replicas * usage.estimated_monthly_cost
                recs.append(Recommendation(
                    optimization_type=OptimizationType.SCALE_DOWN,
                    priority=Priority.MEDIUM,
                    component_id=comp.id,
                    component_name=comp.name,
                    description=f"{comp.name} is over-provisioned ({usage.utilization_percent}% util with {comp.replicas} replicas)",
                    current_state=f"{comp.replicas} replicas, {usage.utilization_percent}% util",
                    recommended_state=f"{target_replicas} replicas",
                    estimated_monthly_savings=round(savings, 2),
                    risk_level="low",
                    implementation_effort="trivial",
                ))

            # Under-provisioned → scale up
            elif usage.is_under_provisioned:
                target_replicas = comp.replicas * 2
                extra_cost = (target_replicas - comp.replicas) / comp.replicas * usage.estimated_monthly_cost
                recs.append(Recommendation(
                    optimization_type=OptimizationType.SCALE_UP,
                    priority=Priority.HIGH,
                    component_id=comp.id,
                    component_name=comp.name,
                    description=f"{comp.name} is under-provisioned ({usage.utilization_percent}% util)",
                    current_state=f"{comp.replicas} replicas, {usage.utilization_percent}% util",
                    recommended_state=f"{target_replicas} replicas",
                    estimated_monthly_savings=-round(extra_cost, 2),  # negative = cost increase
                    risk_level="low",
                    implementation_effort="easy",
                ))

            # No autoscaling → recommend
            if not usage.has_autoscaling and comp.replicas > 1:
                recs.append(Recommendation(
                    optimization_type=OptimizationType.ADD_AUTOSCALING,
                    priority=Priority.LOW,
                    component_id=comp.id,
                    component_name=comp.name,
                    description=f"{comp.name} has {comp.replicas} static replicas without autoscaling",
                    current_state=f"{comp.replicas} static replicas",
                    recommended_state="Enable autoscaling (min=1, max={})".format(comp.replicas * 2),
                    estimated_monthly_savings=round(usage.estimated_monthly_cost * 0.2, 2),
                    risk_level="low",
                    implementation_effort="moderate",
                ))

        return recs
