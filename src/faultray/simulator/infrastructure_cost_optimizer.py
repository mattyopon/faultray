"""Infrastructure Cost Optimizer - comprehensive cost optimization with resilience awareness.

Provides deep cost modeling, right-sizing, reserved vs on-demand analysis,
idle resource detection, cost anomaly alerting, savings plan optimization,
multi-AZ cost/benefit analysis, and total cost of ownership (TCO) calculations.

Usage:
    from faultray.simulator.infrastructure_cost_optimizer import InfrastructureCostOptimizer
    optimizer = InfrastructureCostOptimizer(graph)
    report = optimizer.analyze()
    print(f"Monthly cost: ${report.total_monthly_cost:.2f}")
    print(f"Potential savings: ${report.total_potential_savings:.2f}")

CLI:
    faultray infra-cost-optimize model.yaml --json
"""

from __future__ import annotations

import copy
import logging
import math
import statistics
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum

from faultray.model.components import Component, ComponentType
from faultray.model.graph import InfraGraph

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Monthly cost per replica by component type (USD)
COMPUTE_COST_PER_REPLICA: dict[ComponentType, float] = {
    ComponentType.APP_SERVER: 200.0,
    ComponentType.WEB_SERVER: 180.0,
    ComponentType.DATABASE: 500.0,
    ComponentType.CACHE: 150.0,
    ComponentType.QUEUE: 100.0,
    ComponentType.LOAD_BALANCER: 100.0,
    ComponentType.STORAGE: 30.0,
    ComponentType.DNS: 10.0,
    ComponentType.EXTERNAL_API: 0.0,
    ComponentType.CUSTOM: 150.0,
    ComponentType.AI_AGENT: 250.0,
    ComponentType.LLM_ENDPOINT: 600.0,
    ComponentType.TOOL_SERVICE: 150.0,
    ComponentType.AGENT_ORCHESTRATOR: 300.0,
}

# Storage cost per replica per month (USD)
STORAGE_COST_PER_REPLICA: dict[ComponentType, float] = {
    ComponentType.DATABASE: 50.0,
    ComponentType.STORAGE: 20.0,
    ComponentType.CACHE: 10.0,
    ComponentType.APP_SERVER: 5.0,
    ComponentType.WEB_SERVER: 5.0,
    ComponentType.QUEUE: 5.0,
    ComponentType.LOAD_BALANCER: 2.0,
    ComponentType.DNS: 0.0,
    ComponentType.EXTERNAL_API: 0.0,
    ComponentType.CUSTOM: 5.0,
    ComponentType.AI_AGENT: 10.0,
    ComponentType.LLM_ENDPOINT: 5.0,
    ComponentType.TOOL_SERVICE: 5.0,
    ComponentType.AGENT_ORCHESTRATOR: 10.0,
}

# Network cost per replica per month (USD)
NETWORK_COST_PER_REPLICA: dict[ComponentType, float] = {
    ComponentType.LOAD_BALANCER: 30.0,
    ComponentType.APP_SERVER: 15.0,
    ComponentType.WEB_SERVER: 15.0,
    ComponentType.DATABASE: 10.0,
    ComponentType.CACHE: 10.0,
    ComponentType.QUEUE: 5.0,
    ComponentType.STORAGE: 5.0,
    ComponentType.DNS: 2.0,
    ComponentType.EXTERNAL_API: 0.0,
    ComponentType.CUSTOM: 5.0,
    ComponentType.AI_AGENT: 15.0,
    ComponentType.LLM_ENDPOINT: 20.0,
    ComponentType.TOOL_SERVICE: 10.0,
    ComponentType.AGENT_ORCHESTRATOR: 15.0,
}

# Licensing cost per replica per month (USD)
LICENSING_COST_PER_REPLICA: dict[ComponentType, float] = {
    ComponentType.DATABASE: 100.0,
    ComponentType.APP_SERVER: 0.0,
    ComponentType.WEB_SERVER: 0.0,
    ComponentType.CACHE: 0.0,
    ComponentType.QUEUE: 0.0,
    ComponentType.LOAD_BALANCER: 0.0,
    ComponentType.STORAGE: 0.0,
    ComponentType.DNS: 0.0,
    ComponentType.EXTERNAL_API: 0.0,
    ComponentType.CUSTOM: 0.0,
    ComponentType.AI_AGENT: 0.0,
    ComponentType.LLM_ENDPOINT: 0.0,
    ComponentType.TOOL_SERVICE: 0.0,
    ComponentType.AGENT_ORCHESTRATOR: 0.0,
}

# Spot instance discount rate (fraction of on-demand)
SPOT_DISCOUNT_RATE = 0.70

# Reserved instance discount tiers (1-year and 3-year)
RESERVED_1YR_DISCOUNT = 0.30
RESERVED_3YR_DISCOUNT = 0.50

# Multi-AZ cost premium (percentage increase)
MULTI_AZ_PREMIUM_PERCENT = 25.0

# Operational cost per component per month (monitoring, on-call, etc.)
OPERATIONAL_COST_PER_COMPONENT = 50.0

# Idle threshold: utilization below which a resource is considered idle
IDLE_UTILIZATION_THRESHOLD = 5.0

# Right-sizing threshold: utilization below which right-sizing is recommended
RIGHTSIZE_UTILIZATION_THRESHOLD = 30.0

# Savings plan break-even months
SAVINGS_PLAN_BREAKEVEN_MONTHS = 6


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class CostCategory(str, Enum):
    """Categories of infrastructure cost."""

    COMPUTE = "compute"
    STORAGE = "storage"
    NETWORK = "network"
    LICENSING = "licensing"
    OPERATIONAL = "operational"


class PricingModel(str, Enum):
    """Instance pricing models."""

    ON_DEMAND = "on_demand"
    SPOT = "spot"
    RESERVED_1YR = "reserved_1yr"
    RESERVED_3YR = "reserved_3yr"
    SAVINGS_PLAN = "savings_plan"


class RecommendationType(str, Enum):
    """Types of cost optimization recommendations."""

    RIGHT_SIZE = "right_size"
    SPOT_OPPORTUNITY = "spot_opportunity"
    RESERVED_INSTANCE = "reserved_instance"
    IDLE_RESOURCE = "idle_resource"
    REDUNDANCY_REDUCTION = "redundancy_reduction"
    MULTI_AZ_OPTIMIZATION = "multi_az_optimization"
    SAVINGS_PLAN = "savings_plan"
    CLEANUP = "cleanup"


class RiskLevel(str, Enum):
    """Risk level of a recommendation."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class ComponentCostBreakdown:
    """Detailed cost breakdown for a single component."""

    component_id: str
    component_type: str
    replicas: int
    compute_cost: float
    storage_cost: float
    network_cost: float
    licensing_cost: float
    operational_cost: float
    total_cost: float
    utilization_percent: float
    pricing_model: str = PricingModel.ON_DEMAND.value
    cost_per_request: float = 0.0


@dataclass
class CostAllocation:
    """Cost allocation entry for a service or team."""

    name: str
    component_ids: list[str] = field(default_factory=list)
    total_cost: float = 0.0
    percent_of_total: float = 0.0


@dataclass
class CostRecommendation:
    """A single cost optimization recommendation."""

    recommendation_type: str
    component_id: str
    description: str
    current_cost: float
    projected_cost: float
    monthly_savings: float
    annual_savings: float
    risk_level: str
    resilience_impact: float
    implementation_effort: str  # "low", "medium", "high"
    confidence: float  # 0.0-1.0


@dataclass
class SpotOpportunity:
    """Spot/preemptible instance opportunity for a component."""

    component_id: str
    current_monthly_cost: float
    spot_monthly_cost: float
    monthly_savings: float
    interruption_risk: str  # "low", "medium", "high"
    is_stateless: bool
    has_autoscaling: bool


@dataclass
class ReservedInstanceAnalysis:
    """Reserved instance vs on-demand analysis for a component."""

    component_id: str
    on_demand_monthly: float
    reserved_1yr_monthly: float
    reserved_3yr_monthly: float
    savings_1yr_monthly: float
    savings_3yr_monthly: float
    breakeven_months_1yr: float
    breakeven_months_3yr: float
    recommendation: str  # "on_demand", "reserved_1yr", "reserved_3yr"


@dataclass
class RedundancyCostAnalysis:
    """Cost analysis of N+1 redundancy vs risk of N."""

    component_id: str
    current_replicas: int
    redundancy_cost: float
    n_config_cost: float
    n_plus1_cost: float
    dependent_count: int
    risk_without_redundancy: str  # "low", "medium", "high", "critical"
    recommendation: str


@dataclass
class MultiAZCostAnalysis:
    """Multi-AZ cost premium vs availability benefit analysis."""

    component_id: str
    single_az_cost: float
    multi_az_cost: float
    premium_cost: float
    premium_percent: float
    availability_benefit: str
    is_stateful: bool
    recommendation: str


@dataclass
class IdleResource:
    """A detected idle resource."""

    component_id: str
    utilization_percent: float
    monthly_cost: float
    idle_since_estimate: str
    recommendation: str


@dataclass
class CostAnomalyThreshold:
    """Cost anomaly detection threshold for a component."""

    component_id: str
    baseline_cost: float
    warning_threshold: float
    critical_threshold: float
    current_cost: float
    is_anomalous: bool
    deviation_percent: float


@dataclass
class SavingsPlanRecommendation:
    """Savings plan optimization recommendation."""

    total_on_demand_cost: float
    recommended_commitment: float
    estimated_savings: float
    savings_percent: float
    coverage_percent: float
    breakeven_months: int
    recommended_term: str  # "1yr" or "3yr"


@dataclass
class TCOAnalysis:
    """Total Cost of Ownership analysis."""

    infrastructure_cost: float
    operational_cost: float
    licensing_cost: float
    personnel_cost: float
    downtime_cost: float
    total_tco: float
    tco_per_component: float
    annual_tco: float


@dataclass
class ResilienceChangeCostImpact:
    """Cost impact of a resilience change (adding replicas, regions, etc.)."""

    change_description: str
    current_cost: float
    projected_cost: float
    cost_delta: float
    resilience_before: float
    resilience_after: float
    resilience_delta: float
    cost_per_resilience_point: float


@dataclass
class InfrastructureCostReport:
    """Complete infrastructure cost optimization report."""

    generated_at: str
    total_monthly_cost: float
    total_annual_cost: float
    cost_breakdowns: list[ComponentCostBreakdown] = field(default_factory=list)
    cost_by_category: dict[str, float] = field(default_factory=dict)
    cost_allocations: list[CostAllocation] = field(default_factory=list)
    recommendations: list[CostRecommendation] = field(default_factory=list)
    spot_opportunities: list[SpotOpportunity] = field(default_factory=list)
    reserved_analyses: list[ReservedInstanceAnalysis] = field(default_factory=list)
    redundancy_analyses: list[RedundancyCostAnalysis] = field(default_factory=list)
    multi_az_analyses: list[MultiAZCostAnalysis] = field(default_factory=list)
    idle_resources: list[IdleResource] = field(default_factory=list)
    anomaly_thresholds: list[CostAnomalyThreshold] = field(default_factory=list)
    savings_plan: SavingsPlanRecommendation | None = None
    tco: TCOAnalysis | None = None
    resilience_cost_impacts: list[ResilienceChangeCostImpact] = field(
        default_factory=list
    )
    total_potential_savings: float = 0.0
    savings_percent: float = 0.0


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


def compute_component_cost(comp: Component) -> ComponentCostBreakdown:
    """Compute the full cost breakdown for a single component."""
    ctype = comp.type
    replicas = comp.replicas

    compute = COMPUTE_COST_PER_REPLICA.get(ctype, 150.0) * replicas
    storage = STORAGE_COST_PER_REPLICA.get(ctype, 5.0) * replicas
    network = NETWORK_COST_PER_REPLICA.get(ctype, 5.0) * replicas
    licensing = LICENSING_COST_PER_REPLICA.get(ctype, 0.0) * replicas
    operational = OPERATIONAL_COST_PER_COMPONENT

    total = compute + storage + network + licensing + operational
    util = comp.utilization()

    rps = comp.capacity.max_rps
    cost_per_req = 0.0
    if rps > 0 and total > 0:
        # Approx requests per month (assuming steady-state)
        monthly_requests = rps * 3600 * 24 * 30
        cost_per_req = total / monthly_requests if monthly_requests > 0 else 0.0

    return ComponentCostBreakdown(
        component_id=comp.id,
        component_type=ctype.value,
        replicas=replicas,
        compute_cost=round(compute, 2),
        storage_cost=round(storage, 2),
        network_cost=round(network, 2),
        licensing_cost=round(licensing, 2),
        operational_cost=round(operational, 2),
        total_cost=round(total, 2),
        utilization_percent=round(util, 1),
        cost_per_request=cost_per_req,
    )


def compute_graph_cost(graph: InfraGraph) -> float:
    """Compute total monthly cost for the entire graph."""
    total = 0.0
    for comp in graph.components.values():
        breakdown = compute_component_cost(comp)
        total += breakdown.total_cost
    return round(total, 2)


def _is_stateless(ctype: ComponentType) -> bool:
    """Determine if a component type is stateless."""
    return ctype in {
        ComponentType.APP_SERVER,
        ComponentType.WEB_SERVER,
        ComponentType.LOAD_BALANCER,
    }


def _is_stateful(ctype: ComponentType) -> bool:
    """Determine if a component type is stateful."""
    return ctype in {
        ComponentType.DATABASE,
        ComponentType.CACHE,
        ComponentType.STORAGE,
    }


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class InfrastructureCostOptimizer:
    """Comprehensive infrastructure cost optimizer.

    Analyzes an infrastructure graph for cost optimization opportunities
    while considering resilience requirements.

    Parameters
    ----------
    graph:
        The infrastructure graph to analyze.
    min_resilience_score:
        Minimum acceptable resilience score when making recommendations.
    utilization_history:
        Optional list of (component_id, utilization_percent) tuples for
        historical utilization data used in right-sizing.
    cost_history:
        Optional list of (component_id, monthly_cost) tuples for
        cost anomaly detection.
    team_allocations:
        Optional dict mapping team/service names to lists of component IDs
        for cost allocation reporting.
    """

    def __init__(
        self,
        graph: InfraGraph,
        min_resilience_score: float = 70.0,
        utilization_history: list[tuple[str, float]] | None = None,
        cost_history: list[tuple[str, float]] | None = None,
        team_allocations: dict[str, list[str]] | None = None,
    ) -> None:
        self.graph = graph
        self.min_resilience_score = min_resilience_score
        self.utilization_history = utilization_history or []
        self.cost_history = cost_history or []
        self.team_allocations = team_allocations or {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def analyze(self) -> InfrastructureCostReport:
        """Run the full cost optimization analysis.

        Returns a comprehensive report with cost breakdowns, recommendations,
        spot opportunities, reserved instance analyses, and more.
        """
        breakdowns = self._compute_all_breakdowns()
        total_monthly = sum(b.total_cost for b in breakdowns)
        total_annual = total_monthly * 12

        cost_by_category = self._aggregate_by_category(breakdowns)
        allocations = self._compute_allocations(breakdowns, total_monthly)
        recommendations = self._generate_recommendations(breakdowns)
        spot_opps = self._identify_spot_opportunities()
        reserved = self._analyze_reserved_instances(breakdowns)
        redundancy = self._analyze_redundancy_costs()
        multi_az = self._analyze_multi_az_costs(breakdowns)
        idle = self._detect_idle_resources(breakdowns)
        anomalies = self._compute_anomaly_thresholds(breakdowns)
        savings_plan = self._recommend_savings_plan(breakdowns, total_monthly)
        tco = self._compute_tco(total_monthly, breakdowns)
        resilience_impacts = self._analyze_resilience_cost_impacts()

        total_savings = sum(r.monthly_savings for r in recommendations)
        savings_pct = (total_savings / total_monthly * 100.0) if total_monthly > 0 else 0.0

        return InfrastructureCostReport(
            generated_at=datetime.now(timezone.utc).isoformat(),
            total_monthly_cost=round(total_monthly, 2),
            total_annual_cost=round(total_annual, 2),
            cost_breakdowns=breakdowns,
            cost_by_category=cost_by_category,
            cost_allocations=allocations,
            recommendations=recommendations,
            spot_opportunities=spot_opps,
            reserved_analyses=reserved,
            redundancy_analyses=redundancy,
            multi_az_analyses=multi_az,
            idle_resources=idle,
            anomaly_thresholds=anomalies,
            savings_plan=savings_plan,
            tco=tco,
            resilience_cost_impacts=resilience_impacts,
            total_potential_savings=round(total_savings, 2),
            savings_percent=round(savings_pct, 1),
        )

    def get_cost_breakdown(self, component_id: str) -> ComponentCostBreakdown | None:
        """Get detailed cost breakdown for a single component."""
        comp = self.graph.get_component(component_id)
        if comp is None:
            return None
        return compute_component_cost(comp)

    def estimate_resilience_change_cost(
        self,
        component_id: str,
        additional_replicas: int = 0,
        enable_failover: bool = False,
        enable_multi_az: bool = False,
    ) -> ResilienceChangeCostImpact | None:
        """Estimate the cost impact of a specific resilience change.

        Parameters
        ----------
        component_id:
            The component to modify.
        additional_replicas:
            Number of replicas to add (can be negative to remove).
        enable_failover:
            Whether to enable failover.
        enable_multi_az:
            Whether to enable multi-AZ deployment.
        """
        comp = self.graph.get_component(component_id)
        if comp is None:
            return None

        current_breakdown = compute_component_cost(comp)
        current_cost = current_breakdown.total_cost
        current_resilience = self.graph.resilience_score()

        # Build change description
        changes: list[str] = []
        if additional_replicas != 0:
            changes.append(
                f"{'add' if additional_replicas > 0 else 'remove'} "
                f"{abs(additional_replicas)} replica(s)"
            )
        if enable_failover:
            changes.append("enable failover")
        if enable_multi_az:
            changes.append("enable multi-AZ")
        change_desc = f"{component_id}: {', '.join(changes)}" if changes else "no change"

        # Calculate projected cost
        modified = copy.deepcopy(self.graph)
        mod_comp = modified.get_component(component_id)
        if mod_comp is None:
            return None

        new_replicas = max(1, mod_comp.replicas + additional_replicas)
        mod_comp.replicas = new_replicas
        if enable_failover:
            mod_comp.failover.enabled = True
        # Multi-AZ doesn't change the component model but adds premium cost

        projected_breakdown = compute_component_cost(mod_comp)
        projected_cost = projected_breakdown.total_cost
        if enable_multi_az:
            projected_cost *= (1.0 + MULTI_AZ_PREMIUM_PERCENT / 100.0)
            projected_cost = round(projected_cost, 2)

        new_resilience = modified.resilience_score()
        cost_delta = projected_cost - current_cost
        resilience_delta = new_resilience - current_resilience

        cost_per_point = 0.0
        if resilience_delta != 0:
            cost_per_point = cost_delta / resilience_delta

        return ResilienceChangeCostImpact(
            change_description=change_desc,
            current_cost=round(current_cost, 2),
            projected_cost=round(projected_cost, 2),
            cost_delta=round(cost_delta, 2),
            resilience_before=round(current_resilience, 1),
            resilience_after=round(new_resilience, 1),
            resilience_delta=round(resilience_delta, 1),
            cost_per_resilience_point=round(cost_per_point, 2),
        )

    # ------------------------------------------------------------------
    # Cost breakdowns
    # ------------------------------------------------------------------

    def _compute_all_breakdowns(self) -> list[ComponentCostBreakdown]:
        """Compute cost breakdowns for all components."""
        breakdowns: list[ComponentCostBreakdown] = []
        for comp in self.graph.components.values():
            breakdowns.append(compute_component_cost(comp))
        return breakdowns

    def _aggregate_by_category(
        self, breakdowns: list[ComponentCostBreakdown]
    ) -> dict[str, float]:
        """Aggregate costs by category across all components."""
        totals: dict[str, float] = {
            CostCategory.COMPUTE.value: 0.0,
            CostCategory.STORAGE.value: 0.0,
            CostCategory.NETWORK.value: 0.0,
            CostCategory.LICENSING.value: 0.0,
            CostCategory.OPERATIONAL.value: 0.0,
        }
        for b in breakdowns:
            totals[CostCategory.COMPUTE.value] += b.compute_cost
            totals[CostCategory.STORAGE.value] += b.storage_cost
            totals[CostCategory.NETWORK.value] += b.network_cost
            totals[CostCategory.LICENSING.value] += b.licensing_cost
            totals[CostCategory.OPERATIONAL.value] += b.operational_cost
        return {k: round(v, 2) for k, v in totals.items()}

    def _compute_allocations(
        self,
        breakdowns: list[ComponentCostBreakdown],
        total_cost: float,
    ) -> list[CostAllocation]:
        """Compute cost allocations per team/service."""
        if not self.team_allocations:
            return []

        cost_map = {b.component_id: b.total_cost for b in breakdowns}
        allocations: list[CostAllocation] = []

        for name, cids in self.team_allocations.items():
            team_cost = sum(cost_map.get(cid, 0.0) for cid in cids)
            pct = (team_cost / total_cost * 100.0) if total_cost > 0 else 0.0
            allocations.append(
                CostAllocation(
                    name=name,
                    component_ids=list(cids),
                    total_cost=round(team_cost, 2),
                    percent_of_total=round(pct, 1),
                )
            )

        allocations.sort(key=lambda a: a.total_cost, reverse=True)
        return allocations

    # ------------------------------------------------------------------
    # Recommendations
    # ------------------------------------------------------------------

    def _generate_recommendations(
        self, breakdowns: list[ComponentCostBreakdown]
    ) -> list[CostRecommendation]:
        """Generate all cost optimization recommendations."""
        recs: list[CostRecommendation] = []
        recs.extend(self._recommend_right_sizing(breakdowns))
        recs.extend(self._recommend_idle_cleanup(breakdowns))
        recs.extend(self._recommend_redundancy_reduction())
        recs.sort(key=lambda r: r.monthly_savings, reverse=True)
        return recs

    def _recommend_right_sizing(
        self, breakdowns: list[ComponentCostBreakdown]
    ) -> list[CostRecommendation]:
        """Recommend right-sizing for under-utilized components."""
        recs: list[CostRecommendation] = []

        for b in breakdowns:
            if b.utilization_percent > RIGHTSIZE_UTILIZATION_THRESHOLD:
                continue
            if b.total_cost <= 0:
                continue

            # Use utilization to estimate potential savings
            # If 20% utilized, could potentially downsize by ~50%
            util = max(b.utilization_percent, 1.0)
            reduction_factor = min(0.5, (RIGHTSIZE_UTILIZATION_THRESHOLD - util) / 100.0)
            savings = b.total_cost * reduction_factor

            if savings < 5.0:
                continue

            projected = b.total_cost - savings

            # Check resilience impact
            impact = self._resilience_impact_of_downsize(b.component_id)

            risk = RiskLevel.LOW.value
            if b.utilization_percent < IDLE_UTILIZATION_THRESHOLD:
                risk = RiskLevel.MEDIUM.value
            if impact < -5.0:
                risk = RiskLevel.HIGH.value

            recs.append(
                CostRecommendation(
                    recommendation_type=RecommendationType.RIGHT_SIZE.value,
                    component_id=b.component_id,
                    description=(
                        f"Right-size {b.component_id}: utilization at "
                        f"{b.utilization_percent:.0f}%, potential "
                        f"{reduction_factor * 100:.0f}% cost reduction"
                    ),
                    current_cost=round(b.total_cost, 2),
                    projected_cost=round(projected, 2),
                    monthly_savings=round(savings, 2),
                    annual_savings=round(savings * 12, 2),
                    risk_level=risk,
                    resilience_impact=round(impact, 1),
                    implementation_effort="medium",
                    confidence=round(1.0 - util / 100.0, 2),
                )
            )

        return recs

    def _recommend_idle_cleanup(
        self, breakdowns: list[ComponentCostBreakdown]
    ) -> list[CostRecommendation]:
        """Recommend cleanup for idle resources."""
        recs: list[CostRecommendation] = []

        for b in breakdowns:
            if b.utilization_percent > IDLE_UTILIZATION_THRESHOLD:
                continue
            if b.total_cost <= 0:
                continue

            comp = self.graph.get_component(b.component_id)
            if comp is None:
                continue

            dependents = self.graph.get_dependents(b.component_id)
            if len(dependents) > 0:
                # Cannot simply remove if others depend on it
                continue

            savings = b.total_cost
            impact = self._resilience_impact_of_removal(b.component_id)

            recs.append(
                CostRecommendation(
                    recommendation_type=RecommendationType.IDLE_RESOURCE.value,
                    component_id=b.component_id,
                    description=(
                        f"Idle resource {b.component_id}: utilization "
                        f"{b.utilization_percent:.1f}%, no dependents. "
                        f"Consider decommissioning."
                    ),
                    current_cost=round(b.total_cost, 2),
                    projected_cost=0.0,
                    monthly_savings=round(savings, 2),
                    annual_savings=round(savings * 12, 2),
                    risk_level=RiskLevel.MEDIUM.value,
                    resilience_impact=round(impact, 1),
                    implementation_effort="low",
                    confidence=0.8,
                )
            )

        return recs

    def _recommend_redundancy_reduction(self) -> list[CostRecommendation]:
        """Recommend reducing redundancy where safe."""
        recs: list[CostRecommendation] = []

        for comp in self.graph.components.values():
            if comp.replicas <= 2:
                continue

            dependents = self.graph.get_dependents(comp.id)
            if len(dependents) > 2:
                # Too many dependents, risky to reduce
                continue

            new_replicas = comp.replicas - 1
            current_breakdown = compute_component_cost(comp)
            current_cost = current_breakdown.total_cost

            # Compute projected cost with one fewer replica
            modified = copy.deepcopy(self.graph)
            mod_comp = modified.get_component(comp.id)
            if mod_comp is None:
                continue
            mod_comp.replicas = new_replicas
            projected_breakdown = compute_component_cost(mod_comp)
            projected_cost = projected_breakdown.total_cost

            savings = current_cost - projected_cost
            if savings <= 0:
                continue

            new_score = modified.resilience_score()
            current_score = self.graph.resilience_score()
            impact = new_score - current_score

            risk = RiskLevel.LOW.value
            if new_score < self.min_resilience_score:
                risk = RiskLevel.HIGH.value
            elif impact < -3.0:
                risk = RiskLevel.MEDIUM.value

            recs.append(
                CostRecommendation(
                    recommendation_type=RecommendationType.REDUNDANCY_REDUCTION.value,
                    component_id=comp.id,
                    description=(
                        f"Reduce {comp.id} replicas from {comp.replicas} to "
                        f"{new_replicas} (saves ${savings:.0f}/mo)"
                    ),
                    current_cost=round(current_cost, 2),
                    projected_cost=round(projected_cost, 2),
                    monthly_savings=round(savings, 2),
                    annual_savings=round(savings * 12, 2),
                    risk_level=risk,
                    resilience_impact=round(impact, 1),
                    implementation_effort="low",
                    confidence=0.9,
                )
            )

        return recs

    # ------------------------------------------------------------------
    # Spot instance analysis
    # ------------------------------------------------------------------

    def _identify_spot_opportunities(self) -> list[SpotOpportunity]:
        """Identify components suitable for spot/preemptible instances."""
        opportunities: list[SpotOpportunity] = []

        for comp in self.graph.components.values():
            is_sl = _is_stateless(comp.type)
            if not is_sl:
                continue
            if comp.replicas < 2:
                continue

            breakdown = compute_component_cost(comp)
            current_cost = breakdown.compute_cost  # Only compute is spot-eligible
            spot_cost = current_cost * (1.0 - SPOT_DISCOUNT_RATE)
            savings = current_cost - spot_cost

            if savings <= 0:
                continue

            has_as = comp.autoscaling.enabled

            if has_as:
                interrupt_risk = "low"
            elif comp.replicas >= 3:
                interrupt_risk = "medium"
            else:
                interrupt_risk = "high"

            opportunities.append(
                SpotOpportunity(
                    component_id=comp.id,
                    current_monthly_cost=round(current_cost, 2),
                    spot_monthly_cost=round(spot_cost, 2),
                    monthly_savings=round(savings, 2),
                    interruption_risk=interrupt_risk,
                    is_stateless=is_sl,
                    has_autoscaling=has_as,
                )
            )

        opportunities.sort(key=lambda o: o.monthly_savings, reverse=True)
        return opportunities

    # ------------------------------------------------------------------
    # Reserved instance analysis
    # ------------------------------------------------------------------

    def _analyze_reserved_instances(
        self, breakdowns: list[ComponentCostBreakdown]
    ) -> list[ReservedInstanceAnalysis]:
        """Analyze reserved instance vs on-demand for each component."""
        analyses: list[ReservedInstanceAnalysis] = []

        for b in breakdowns:
            if b.compute_cost <= 0:
                continue

            on_demand = b.compute_cost
            reserved_1yr = on_demand * (1.0 - RESERVED_1YR_DISCOUNT)
            reserved_3yr = on_demand * (1.0 - RESERVED_3YR_DISCOUNT)
            savings_1yr = on_demand - reserved_1yr
            savings_3yr = on_demand - reserved_3yr

            # Break-even = upfront premium / monthly savings
            # For reserved: upfront = 0 (simplified), so breakeven is immediate
            # In practice, reserved has a commitment period
            breakeven_1yr = 12.0 * (1.0 - RESERVED_1YR_DISCOUNT) / RESERVED_1YR_DISCOUNT
            breakeven_3yr = 36.0 * (1.0 - RESERVED_3YR_DISCOUNT) / RESERVED_3YR_DISCOUNT

            comp = self.graph.get_component(b.component_id)
            util = b.utilization_percent if comp else 0.0

            # Recommendation logic
            if util >= 50.0:
                recommendation = "reserved_3yr"
            elif util >= 30.0:
                recommendation = "reserved_1yr"
            else:
                recommendation = "on_demand"

            analyses.append(
                ReservedInstanceAnalysis(
                    component_id=b.component_id,
                    on_demand_monthly=round(on_demand, 2),
                    reserved_1yr_monthly=round(reserved_1yr, 2),
                    reserved_3yr_monthly=round(reserved_3yr, 2),
                    savings_1yr_monthly=round(savings_1yr, 2),
                    savings_3yr_monthly=round(savings_3yr, 2),
                    breakeven_months_1yr=round(breakeven_1yr, 1),
                    breakeven_months_3yr=round(breakeven_3yr, 1),
                    recommendation=recommendation,
                )
            )

        return analyses

    # ------------------------------------------------------------------
    # Redundancy cost analysis
    # ------------------------------------------------------------------

    def _analyze_redundancy_costs(self) -> list[RedundancyCostAnalysis]:
        """Analyze cost of N+1 redundancy vs risk of N for each component."""
        analyses: list[RedundancyCostAnalysis] = []

        for comp in self.graph.components.values():
            breakdown = compute_component_cost(comp)
            total_cost = breakdown.total_cost

            # Cost with one fewer replica (N configuration)
            per_replica_cost = total_cost / comp.replicas if comp.replicas > 0 else 0.0
            n_cost = total_cost - per_replica_cost  # N replicas cost
            n_plus1_cost = total_cost  # Current cost is N+1 if replicas > 1
            redundancy_premium = per_replica_cost

            if comp.replicas <= 1:
                n_cost = total_cost
                n_plus1_cost = total_cost + per_replica_cost
                redundancy_premium = per_replica_cost

            dependents = self.graph.get_dependents(comp.id)
            dep_count = len(dependents)

            # Determine risk level
            if comp.replicas <= 1 and dep_count > 0:
                risk = "critical"
            elif comp.replicas <= 1:
                risk = "high"
            elif dep_count > 2:
                risk = "medium"
            else:
                risk = "low"

            # Recommendation
            if risk in ("critical", "high"):
                rec = f"Maintain or increase redundancy for {comp.id}"
            elif comp.replicas > 3 and dep_count <= 1:
                rec = f"Consider reducing {comp.id} to {comp.replicas - 1} replicas"
            else:
                rec = f"Current redundancy for {comp.id} is appropriate"

            analyses.append(
                RedundancyCostAnalysis(
                    component_id=comp.id,
                    current_replicas=comp.replicas,
                    redundancy_cost=round(redundancy_premium, 2),
                    n_config_cost=round(n_cost, 2),
                    n_plus1_cost=round(n_plus1_cost, 2),
                    dependent_count=dep_count,
                    risk_without_redundancy=risk,
                    recommendation=rec,
                )
            )

        return analyses

    # ------------------------------------------------------------------
    # Multi-AZ analysis
    # ------------------------------------------------------------------

    def _analyze_multi_az_costs(
        self, breakdowns: list[ComponentCostBreakdown]
    ) -> list[MultiAZCostAnalysis]:
        """Analyze multi-AZ cost premium vs availability benefit."""
        analyses: list[MultiAZCostAnalysis] = []
        cost_map = {b.component_id: b.total_cost for b in breakdowns}

        for comp in self.graph.components.values():
            base_cost = cost_map.get(comp.id, 0.0)
            if base_cost <= 0:
                continue

            multi_az_cost = base_cost * (1.0 + MULTI_AZ_PREMIUM_PERCENT / 100.0)
            premium = multi_az_cost - base_cost

            is_sf = _is_stateful(comp.type)

            # Determine availability benefit
            bool(comp.region.availability_zone)
            dependents = self.graph.get_dependents(comp.id)

            if is_sf and len(dependents) > 0:
                benefit = "high"
                recommendation = f"Multi-AZ strongly recommended for {comp.id}"
            elif is_sf:
                benefit = "medium"
                recommendation = f"Multi-AZ recommended for stateful {comp.id}"
            elif len(dependents) > 2:
                benefit = "medium"
                recommendation = f"Multi-AZ optional for {comp.id} (many dependents)"
            else:
                benefit = "low"
                recommendation = (
                    f"Multi-AZ optional for {comp.id} (stateless, few dependents)"
                )

            analyses.append(
                MultiAZCostAnalysis(
                    component_id=comp.id,
                    single_az_cost=round(base_cost, 2),
                    multi_az_cost=round(multi_az_cost, 2),
                    premium_cost=round(premium, 2),
                    premium_percent=MULTI_AZ_PREMIUM_PERCENT,
                    availability_benefit=benefit,
                    is_stateful=is_sf,
                    recommendation=recommendation,
                )
            )

        return analyses

    # ------------------------------------------------------------------
    # Idle resource detection
    # ------------------------------------------------------------------

    def _detect_idle_resources(
        self, breakdowns: list[ComponentCostBreakdown]
    ) -> list[IdleResource]:
        """Detect idle resources based on utilization data."""
        idle_list: list[IdleResource] = []

        for b in breakdowns:
            if b.utilization_percent > IDLE_UTILIZATION_THRESHOLD:
                continue
            if b.total_cost <= 0:
                continue

            # Estimate idle duration from history if available
            hist_entries = [
                u for cid, u in self.utilization_history if cid == b.component_id
            ]
            if hist_entries and all(u <= IDLE_UTILIZATION_THRESHOLD for u in hist_entries):
                idle_since = "extended period (based on history)"
            elif hist_entries:
                idle_since = "recent (partial history shows activity)"
            else:
                idle_since = "unknown (no historical data)"

            dependents = self.graph.get_dependents(b.component_id)
            if len(dependents) > 0:
                rec = (
                    f"Resource {b.component_id} appears idle but has "
                    f"{len(dependents)} dependent(s). Verify before cleanup."
                )
            else:
                rec = (
                    f"Resource {b.component_id} appears idle with no dependents. "
                    f"Consider decommissioning to save ${b.total_cost:.0f}/mo."
                )

            idle_list.append(
                IdleResource(
                    component_id=b.component_id,
                    utilization_percent=round(b.utilization_percent, 1),
                    monthly_cost=round(b.total_cost, 2),
                    idle_since_estimate=idle_since,
                    recommendation=rec,
                )
            )

        idle_list.sort(key=lambda r: r.monthly_cost, reverse=True)
        return idle_list

    # ------------------------------------------------------------------
    # Cost anomaly thresholds
    # ------------------------------------------------------------------

    def _compute_anomaly_thresholds(
        self, breakdowns: list[ComponentCostBreakdown]
    ) -> list[CostAnomalyThreshold]:
        """Compute cost anomaly alerting thresholds for each component."""
        thresholds: list[CostAnomalyThreshold] = []

        # Group cost history by component
        history_map: dict[str, list[float]] = {}
        for cid, cost in self.cost_history:
            history_map.setdefault(cid, []).append(cost)

        for b in breakdowns:
            baseline = b.total_cost
            hist = history_map.get(b.component_id, [])

            if len(hist) >= 2:
                mean_cost = statistics.mean(hist)
                std_cost = statistics.stdev(hist)
                baseline = mean_cost
                warning = mean_cost + 2.0 * std_cost
                critical = mean_cost + 3.0 * std_cost
            else:
                warning = baseline * 1.5
                critical = baseline * 2.0

            deviation = 0.0
            if baseline > 0:
                deviation = ((b.total_cost - baseline) / baseline) * 100.0

            is_anomalous = b.total_cost > warning

            thresholds.append(
                CostAnomalyThreshold(
                    component_id=b.component_id,
                    baseline_cost=round(baseline, 2),
                    warning_threshold=round(warning, 2),
                    critical_threshold=round(critical, 2),
                    current_cost=round(b.total_cost, 2),
                    is_anomalous=is_anomalous,
                    deviation_percent=round(deviation, 1),
                )
            )

        return thresholds

    # ------------------------------------------------------------------
    # Savings plan
    # ------------------------------------------------------------------

    def _recommend_savings_plan(
        self,
        breakdowns: list[ComponentCostBreakdown],
        total_monthly: float,
    ) -> SavingsPlanRecommendation | None:
        """Recommend a savings plan based on current usage patterns."""
        if total_monthly <= 0:
            return None

        # Only include compute costs for savings plan
        total_compute = sum(b.compute_cost for b in breakdowns)
        if total_compute <= 0:
            return None

        # Determine stable workloads (utilization > 30%)
        stable_compute = 0.0
        for b in breakdowns:
            if b.utilization_percent >= RIGHTSIZE_UTILIZATION_THRESHOLD:
                stable_compute += b.compute_cost

        coverage = (stable_compute / total_compute * 100.0) if total_compute > 0 else 0.0

        # Recommend commitment level (70-80% of stable workload)
        commitment = stable_compute * 0.75
        savings_rate = RESERVED_1YR_DISCOUNT if coverage < 70 else RESERVED_3YR_DISCOUNT
        estimated_savings = commitment * savings_rate
        savings_pct = (estimated_savings / total_compute * 100.0) if total_compute > 0 else 0.0

        term = "3yr" if coverage >= 70 else "1yr"

        return SavingsPlanRecommendation(
            total_on_demand_cost=round(total_compute, 2),
            recommended_commitment=round(commitment, 2),
            estimated_savings=round(estimated_savings, 2),
            savings_percent=round(savings_pct, 1),
            coverage_percent=round(coverage, 1),
            breakeven_months=SAVINGS_PLAN_BREAKEVEN_MONTHS,
            recommended_term=term,
        )

    # ------------------------------------------------------------------
    # TCO
    # ------------------------------------------------------------------

    def _compute_tco(
        self,
        total_monthly: float,
        breakdowns: list[ComponentCostBreakdown],
    ) -> TCOAnalysis:
        """Compute Total Cost of Ownership including operational costs."""
        infra_cost = total_monthly
        operational_cost = sum(b.operational_cost for b in breakdowns)
        licensing_cost = sum(b.licensing_cost for b in breakdowns)

        # Estimate personnel cost based on component count
        comp_count = len(breakdowns)
        # Rule of thumb: 1 engineer per 10 components at $10k/mo
        personnel_cost = math.ceil(comp_count / 10) * 10000.0 if comp_count > 0 else 0.0

        # Estimate downtime cost from cost profiles
        downtime_cost = 0.0
        for comp in self.graph.components.values():
            cp = comp.cost_profile
            if cp.revenue_per_minute > 0:
                # Estimate monthly downtime from MTBF/MTTR
                mtbf_h = comp.operational_profile.mtbf_hours
                mttr_m = comp.operational_profile.mttr_minutes
                if mtbf_h > 0:
                    incidents_per_month = (30 * 24) / mtbf_h
                    downtime_minutes = incidents_per_month * mttr_m
                    downtime_cost += downtime_minutes * cp.revenue_per_minute

        total_tco = infra_cost + operational_cost + licensing_cost + personnel_cost + downtime_cost
        tco_per_comp = total_tco / comp_count if comp_count > 0 else 0.0

        return TCOAnalysis(
            infrastructure_cost=round(infra_cost, 2),
            operational_cost=round(operational_cost, 2),
            licensing_cost=round(licensing_cost, 2),
            personnel_cost=round(personnel_cost, 2),
            downtime_cost=round(downtime_cost, 2),
            total_tco=round(total_tco, 2),
            tco_per_component=round(tco_per_comp, 2),
            annual_tco=round(total_tco * 12, 2),
        )

    # ------------------------------------------------------------------
    # Resilience cost impact
    # ------------------------------------------------------------------

    def _analyze_resilience_cost_impacts(self) -> list[ResilienceChangeCostImpact]:
        """Analyze cost impact of common resilience changes."""
        impacts: list[ResilienceChangeCostImpact] = []

        for comp in self.graph.components.values():
            # Scenario: add one replica
            impact = self.estimate_resilience_change_cost(
                comp.id, additional_replicas=1
            )
            if impact is not None and impact.cost_delta != 0:
                impacts.append(impact)

        # Sort by cost-effectiveness (cost per resilience point, ascending)
        impacts.sort(
            key=lambda i: abs(i.cost_per_resilience_point)
            if i.cost_per_resilience_point != 0
            else float("inf")
        )

        return impacts

    # ------------------------------------------------------------------
    # Impact helpers
    # ------------------------------------------------------------------

    def _resilience_impact_of_downsize(self, component_id: str) -> float:
        """Estimate resilience impact of downsizing a component.

        Downsizing does not change replica count, so impact is typically 0
        unless capacity constraints become an issue.
        """
        comp = self.graph.get_component(component_id)
        if comp is None:
            return 0.0
        # Downsizing doesn't change graph topology; impact is near-zero
        return 0.0

    def _resilience_impact_of_removal(self, component_id: str) -> float:
        """Estimate resilience impact of removing a component entirely."""
        modified = copy.deepcopy(self.graph)
        mod_comp = modified.get_component(component_id)
        if mod_comp is None:
            return 0.0

        # Simulate removal by setting replicas to 0 health
        from faultray.model.components import HealthStatus

        mod_comp.health = HealthStatus.DOWN
        original_score = self.graph.resilience_score()
        new_score = modified.resilience_score()
        return new_score - original_score
