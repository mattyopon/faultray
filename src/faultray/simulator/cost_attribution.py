"""Failure Cost Attribution Engine.

Attributes the financial cost of potential infrastructure failures to
specific teams, services, and components. Helps organizations understand:
- Which team owns the most risk?
- Which service has the highest cost-of-failure?
- What's the ROI of improving a specific component?
- How should resilience budget be allocated?
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field

from faultray.model.graph import InfraGraph

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Hours per year for annualized calculations.
HOURS_PER_YEAR = 8760.0

# Default estimated improvement cost per component (for ROI calculations).
_DEFAULT_IMPROVEMENT_COST = 10_000.0

# Conservative uptime/downtime assumptions by replica count.
# Single instance: ~99.9% uptime -> ~8.76h/year downtime
# 2 replicas:      ~99.99% -> ~0.876h/year
# 3+ replicas:     ~99.999% -> ~0.088h/year
_DOWNTIME_BY_REPLICAS: dict[int, float] = {
    1: 8.76,
    2: 0.876,
    3: 0.088,
}

# Team name pattern mapping for auto-assignment.
_TEAM_PATTERNS: list[tuple[list[str], str]] = [
    (["api-", "api_", "web-", "web_", "app-", "app_", "backend-", "backend_", "service-", "service_"], "backend"),
    (["db-", "db_", "postgres", "mysql", "redis", "mongo", "elastic", "cache-", "cache_", "memcache"], "data"),
    (["lb-", "lb_", "nginx", "haproxy", "cdn", "dns", "gateway", "ingress", "proxy"], "infra"),
    (["queue", "kafka", "rabbit", "sqs", "sns", "pubsub"], "messaging"),
]


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class CostModel:
    """Financial parameters for cost attribution."""

    revenue_per_hour: float  # Total company revenue per hour
    cost_per_incident: float = 50_000.0  # Average incident cost (people, reputation)
    sla_penalty_per_hour: float = 0.0  # SLA breach penalty rate per hour
    customer_count: int = 0  # For per-customer impact calculation
    currency: str = "USD"


@dataclass
class ComponentCostProfile:
    """Cost attribution for a single component."""

    component_id: str
    component_name: str
    owner_team: str
    annual_failure_probability: float
    estimated_downtime_hours: float
    direct_cost: float  # Cost if this component alone fails
    cascade_cost: float  # Cost including cascade impact
    total_annual_risk: float  # probability x cost
    percentage_of_total_risk: float
    improvement_roi: float  # Cost saved per $ invested in improving


@dataclass
class TeamRiskProfile:
    """Aggregated risk for a team."""

    team_name: str
    owned_components: list[str] = field(default_factory=list)
    total_annual_risk: float = 0.0
    highest_risk_component: str = ""
    percentage_of_total_risk: float = 0.0
    recommended_budget: float = 0.0


@dataclass
class CostAttributionReport:
    """Complete cost attribution analysis."""

    total_annual_risk: float = 0.0
    component_profiles: list[ComponentCostProfile] = field(default_factory=list)
    team_profiles: list[TeamRiskProfile] = field(default_factory=list)
    top_risk_components: list[ComponentCostProfile] = field(default_factory=list)
    cost_reduction_opportunities: list[tuple[str, float, str]] = field(default_factory=list)
    budget_allocation: dict[str, float] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def _auto_assign_team(component_id: str) -> str:
    """Assign a team name based on component ID patterns."""
    comp_lower = component_id.lower()
    for patterns, team in _TEAM_PATTERNS:
        for pattern in patterns:
            if comp_lower.startswith(pattern) or pattern in comp_lower:
                return team
    return "platform"


def _estimate_failure_probability(
    replicas: int,
    has_failover: bool,
    has_autoscaling: bool,
    mtbf_hours: float = 0.0,
) -> float:
    """Estimate annual failure probability for a component.

    Conservative estimates based on industry data:
    - Single instance with no protection: ~10 failures/year
    - With failover: reduces by 80%
    - With autoscaling: reduces capacity-related failures by 50%
    - Multiple replicas: reduces by order of magnitude per replica

    Returns probability between 0 and 1.
    """
    # Base failure rate from MTBF if available
    if mtbf_hours > 0:
        # Expected failures per year = HOURS_PER_YEAR / MTBF
        base_failures = HOURS_PER_YEAR / mtbf_hours
    else:
        # Default: assume ~10 incidents/year for single instance
        base_failures = 10.0

    # Replica reduction
    if replicas >= 3:
        base_failures *= 0.01  # 99% reduction for 3+ replicas
    elif replicas >= 2:
        base_failures *= 0.1  # 90% reduction for 2 replicas

    # Failover reduction
    if has_failover:
        base_failures *= 0.2  # 80% reduction

    # Autoscaling reduction (capacity-related only, ~50% of failures)
    if has_autoscaling:
        base_failures *= 0.5  # 50% reduction

    # Convert to probability (cap at 1.0)
    # probability = 1 - e^(-failures_per_year) for Poisson model
    probability = 1.0 - math.exp(-base_failures)
    return min(1.0, probability)


def _estimate_downtime_hours(
    replicas: int,
    has_failover: bool,
    mttr_minutes: float = 30.0,
) -> float:
    """Estimate per-incident downtime in hours.

    Conservative approach:
    - Single instance: full MTTR
    - With failover: promotion time only (typically much shorter)
    - Multiple replicas: reduced impact during failover
    """
    base_downtime = mttr_minutes / 60.0

    if replicas >= 2 and has_failover:
        # Both replicas and failover: minimal downtime
        return base_downtime * 0.1
    elif has_failover:
        # Failover only: promotion time
        return base_downtime * 0.3
    elif replicas >= 2:
        # Replicas but no failover: some requests may succeed
        return base_downtime * 0.5

    return base_downtime


def _estimate_traffic_fraction(
    graph: InfraGraph, component_id: str,
) -> float:
    """Estimate what fraction of traffic flows through a component.

    Uses the dependency graph to determine how critical the component is:
    - Components with many dependents handle more traffic
    - Entry-point components (no upstream) are considered to handle all traffic
    """
    total = len(graph.components)
    if total == 0:
        return 0.0

    dependents = graph.get_dependents(component_id)
    if not dependents:
        # If nobody depends on this component AND it depends on others,
        # it's likely an entry point (e.g., load balancer)
        dependencies = graph.get_dependencies(component_id)
        if dependencies:
            return 1.0
        # Isolated component
        return 1.0 / total

    # Fraction based on how many components are affected if this one fails
    affected = graph.get_all_affected(component_id)
    return min(1.0, (len(affected) + 1) / total)


# ---------------------------------------------------------------------------
# CostAttributionEngine
# ---------------------------------------------------------------------------

class CostAttributionEngine:
    """Attributes failure cost to teams, services, and components."""

    def analyze(
        self,
        graph: InfraGraph,
        cost_model: CostModel,
        team_mapping: dict[str, str] | None = None,
    ) -> CostAttributionReport:
        """Run full cost attribution analysis.

        Args:
            graph: Infrastructure graph to analyze.
            cost_model: Financial parameters.
            team_mapping: Optional component_id -> team_name mapping.
                          Auto-assigns by naming patterns if None.

        Returns:
            CostAttributionReport with all attributions.
        """
        if not graph.components:
            return CostAttributionReport()

        if team_mapping is None:
            team_mapping = {
                cid: _auto_assign_team(cid) for cid in graph.components
            }

        # Calculate per-component cost profiles
        component_profiles: list[ComponentCostProfile] = []
        for comp_id in graph.components:
            profile = self.calculate_component_cost(
                graph, comp_id, cost_model, team_mapping.get(comp_id, "platform"),
            )
            component_profiles.append(profile)

        # Calculate total annual risk
        total_risk = sum(p.total_annual_risk for p in component_profiles)

        # Set percentage of total risk
        for profile in component_profiles:
            if total_risk > 0:
                profile.percentage_of_total_risk = round(
                    (profile.total_annual_risk / total_risk) * 100.0, 2,
                )

        # Sort by total annual risk descending
        component_profiles.sort(key=lambda p: p.total_annual_risk, reverse=True)

        # Top 5 risk components
        top_risk = component_profiles[:5]

        # Build team profiles
        team_profiles = self._build_team_profiles(
            component_profiles, total_risk,
        )

        # Cost reduction opportunities
        opportunities = self._find_opportunities(
            graph, component_profiles, cost_model,
        )

        # Budget allocation
        budget_allocation = {
            tp.team_name: round(tp.recommended_budget, 2)
            for tp in team_profiles
        }

        return CostAttributionReport(
            total_annual_risk=round(total_risk, 2),
            component_profiles=component_profiles,
            team_profiles=team_profiles,
            top_risk_components=top_risk,
            cost_reduction_opportunities=opportunities,
            budget_allocation=budget_allocation,
        )

    def calculate_component_cost(
        self,
        graph: InfraGraph,
        component_id: str,
        cost_model: CostModel,
        owner_team: str = "platform",
    ) -> ComponentCostProfile:
        """Calculate cost attribution for a single component.

        Args:
            graph: Infrastructure graph.
            component_id: Component to analyze.
            cost_model: Financial parameters.
            owner_team: Team that owns this component.

        Returns:
            ComponentCostProfile with cost breakdown.
        """
        comp = graph.get_component(component_id)
        if comp is None:
            return ComponentCostProfile(
                component_id=component_id,
                component_name=component_id,
                owner_team=owner_team,
                annual_failure_probability=0.0,
                estimated_downtime_hours=0.0,
                direct_cost=0.0,
                cascade_cost=0.0,
                total_annual_risk=0.0,
                percentage_of_total_risk=0.0,
                improvement_roi=0.0,
            )

        # Failure probability
        failure_prob = _estimate_failure_probability(
            replicas=comp.replicas,
            has_failover=comp.failover.enabled,
            has_autoscaling=comp.autoscaling.enabled,
            mtbf_hours=comp.operational_profile.mtbf_hours,
        )

        # Per-incident downtime
        downtime = _estimate_downtime_hours(
            replicas=comp.replicas,
            has_failover=comp.failover.enabled,
            mttr_minutes=comp.operational_profile.mttr_minutes,
        )

        # Traffic fraction for this component
        traffic_fraction = _estimate_traffic_fraction(graph, component_id)

        # Direct cost = downtime * (revenue_per_hour * traffic_fraction + sla_penalty)
        direct_cost = downtime * (
            cost_model.revenue_per_hour * traffic_fraction
            + cost_model.sla_penalty_per_hour
        )

        # Cascade cost: include downstream impact
        affected = graph.get_all_affected(component_id)
        cascade_multiplier = 1.0
        for affected_id in affected:
            affected_comp = graph.get_component(affected_id)
            if affected_comp is None:
                continue
            # Each affected component adds a fraction of its traffic impact
            affected_fraction = _estimate_traffic_fraction(graph, affected_id)
            cascade_multiplier += affected_fraction * 0.5  # Conservative: 50% cascade

        cascade_cost = direct_cost * cascade_multiplier

        # Total annual risk = failure_probability * total_cost + incident cost
        incident_cost = cost_model.cost_per_incident * failure_prob
        total_annual_risk = failure_prob * cascade_cost + incident_cost

        # Improvement ROI: estimated savings from adding 1 replica
        improved_prob = _estimate_failure_probability(
            replicas=comp.replicas + 1,
            has_failover=comp.failover.enabled,
            has_autoscaling=comp.autoscaling.enabled,
            mtbf_hours=comp.operational_profile.mtbf_hours,
        )
        improved_risk = improved_prob * cascade_cost + cost_model.cost_per_incident * improved_prob
        risk_reduction = total_annual_risk - improved_risk
        improvement_roi = risk_reduction / _DEFAULT_IMPROVEMENT_COST if risk_reduction > 0 else 0.0

        return ComponentCostProfile(
            component_id=component_id,
            component_name=comp.name,
            owner_team=owner_team,
            annual_failure_probability=round(failure_prob, 6),
            estimated_downtime_hours=round(downtime, 3),
            direct_cost=round(direct_cost, 2),
            cascade_cost=round(cascade_cost, 2),
            total_annual_risk=round(total_annual_risk, 2),
            percentage_of_total_risk=0.0,  # Set later when total is known
            improvement_roi=round(improvement_roi, 2),
        )

    def get_roi_ranking(
        self,
        graph: InfraGraph,
        cost_model: CostModel,
    ) -> list[tuple[str, float]]:
        """Rank components by improvement ROI.

        Args:
            graph: Infrastructure graph.
            cost_model: Financial parameters.

        Returns:
            List of (component_id, roi_value) sorted by ROI descending.
        """
        report = self.analyze(graph, cost_model)
        ranking = [
            (p.component_id, p.improvement_roi)
            for p in report.component_profiles
            if p.improvement_roi > 0
        ]
        ranking.sort(key=lambda x: x[1], reverse=True)
        return ranking

    def estimate_improvement_savings(
        self,
        graph: InfraGraph,
        cost_model: CostModel,
        changes: list[str],
    ) -> float:
        """Estimate annual savings from improving specific components.

        Args:
            graph: Infrastructure graph.
            cost_model: Financial parameters.
            changes: List of component IDs to improve.

        Returns:
            Estimated annual cost savings.
        """
        total_savings = 0.0
        for comp_id in changes:
            comp = graph.get_component(comp_id)
            if comp is None:
                continue

            # Current cost
            current = self.calculate_component_cost(graph, comp_id, cost_model)

            # Improved cost (simulate adding a replica)
            improved_prob = _estimate_failure_probability(
                replicas=comp.replicas + 1,
                has_failover=comp.failover.enabled,
                has_autoscaling=comp.autoscaling.enabled,
                mtbf_hours=comp.operational_profile.mtbf_hours,
            )

            improved_downtime = _estimate_downtime_hours(
                replicas=comp.replicas + 1,
                has_failover=comp.failover.enabled,
                mttr_minutes=comp.operational_profile.mttr_minutes,
            )

            traffic_fraction = _estimate_traffic_fraction(graph, comp_id)
            improved_direct = improved_downtime * (
                cost_model.revenue_per_hour * traffic_fraction
                + cost_model.sla_penalty_per_hour
            )

            # Cascade
            affected = graph.get_all_affected(comp_id)
            cascade_mult = 1.0
            for aid in affected:
                af = _estimate_traffic_fraction(graph, aid)
                cascade_mult += af * 0.5

            improved_cascade = improved_direct * cascade_mult
            improved_risk = (
                improved_prob * improved_cascade
                + cost_model.cost_per_incident * improved_prob
            )

            savings = current.total_annual_risk - improved_risk
            total_savings += max(0.0, savings)

        return round(total_savings, 2)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_team_profiles(
        self,
        component_profiles: list[ComponentCostProfile],
        total_risk: float,
    ) -> list[TeamRiskProfile]:
        """Aggregate component risks into team profiles."""
        teams: dict[str, TeamRiskProfile] = {}

        for cp in component_profiles:
            team_name = cp.owner_team
            if team_name not in teams:
                teams[team_name] = TeamRiskProfile(team_name=team_name)

            tp = teams[team_name]
            tp.owned_components.append(cp.component_id)
            tp.total_annual_risk += cp.total_annual_risk

            if (
                not tp.highest_risk_component
                or cp.total_annual_risk > self._get_component_risk(
                    component_profiles, tp.highest_risk_component,
                )
            ):
                tp.highest_risk_component = cp.component_id

        # Calculate percentages and recommended budget
        for tp in teams.values():
            tp.total_annual_risk = round(tp.total_annual_risk, 2)
            if total_risk > 0:
                tp.percentage_of_total_risk = round(
                    (tp.total_annual_risk / total_risk) * 100.0, 2,
                )
                # Recommended budget: proportional to risk, capped at risk value
                tp.recommended_budget = round(
                    tp.total_annual_risk * 0.2, 2,  # 20% of risk as budget
                )

        # Sort by total risk descending
        result = sorted(teams.values(), key=lambda t: t.total_annual_risk, reverse=True)
        return result

    def _get_component_risk(
        self,
        profiles: list[ComponentCostProfile],
        component_id: str,
    ) -> float:
        """Look up total_annual_risk for a component."""
        for p in profiles:
            if p.component_id == component_id:
                return p.total_annual_risk
        return 0.0

    def _find_opportunities(
        self,
        graph: InfraGraph,
        profiles: list[ComponentCostProfile],
        cost_model: CostModel,
    ) -> list[tuple[str, float, str]]:
        """Find cost reduction opportunities.

        Returns list of (component_id, estimated_savings, recommended_action).
        """
        opportunities: list[tuple[str, float, str]] = []

        for profile in profiles[:10]:  # Focus on top 10 risk components
            comp = graph.get_component(profile.component_id)
            if comp is None:
                continue

            # Opportunity: add replicas
            if comp.replicas <= 1:
                savings = self.estimate_improvement_savings(
                    graph, cost_model, [profile.component_id],
                )
                if savings > 0:
                    opportunities.append((
                        profile.component_id,
                        savings,
                        f"Add replicas (current: {comp.replicas})",
                    ))

            # Opportunity: enable failover
            if not comp.failover.enabled and comp.replicas >= 2:
                opportunities.append((
                    profile.component_id,
                    profile.total_annual_risk * 0.3,
                    "Enable failover for existing replicas",
                ))

            # Opportunity: enable autoscaling
            if not comp.autoscaling.enabled:
                opportunities.append((
                    profile.component_id,
                    profile.total_annual_risk * 0.15,
                    "Enable autoscaling to handle capacity surges",
                ))

        # Sort by savings descending
        opportunities.sort(key=lambda x: x[1], reverse=True)
        return opportunities[:10]  # Top 10 opportunities
