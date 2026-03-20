# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Business Source License 1.1. See LICENSE file for details.

"""Incident cost calculator — real-time financial impact estimation.

Estimates the financial impact of infrastructure incidents including
direct costs (revenue loss, SLA credits), indirect costs (engineer time,
reputation damage), and opportunity costs (customer churn).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from faultray.model.components import ComponentType
from faultray.model.graph import InfraGraph


class CostCategory(str, Enum):
    """Categories of incident cost."""

    REVENUE_LOSS = "revenue_loss"
    SLA_CREDITS = "sla_credits"
    ENGINEER_TIME = "engineer_time"
    CUSTOMER_CHURN = "customer_churn"
    REPUTATION = "reputation"
    DATA_LOSS = "data_loss"
    REGULATORY_FINE = "regulatory_fine"


@dataclass
class CostBreakdown:
    """Cost breakdown for a single category."""

    category: CostCategory
    amount_usd: float
    description: str
    calculation: str


@dataclass
class ComponentCost:
    """Cost impact for a single component failure."""

    component_id: str
    component_name: str
    component_type: str
    downtime_minutes: int
    breakdowns: list[CostBreakdown]
    total_cost_usd: float
    risk_adjusted_cost: float  # cost × probability


@dataclass
class ScenarioCost:
    """Cost of a specific failure scenario."""

    scenario_name: str
    affected_components: list[str]
    total_downtime_minutes: int
    component_costs: list[ComponentCost]
    total_cost_usd: float
    cost_per_minute: float
    severity: str


@dataclass
class CostReport:
    """Full incident cost analysis."""

    component_costs: list[ComponentCost]
    total_annual_risk_usd: float
    highest_risk_component: str
    highest_risk_cost: float
    cost_by_category: dict[str, float]
    roi_of_improvements: list[dict]
    recommendations: list[str]


# Default cost parameters when not specified on components
_DEFAULT_REVENUE_PER_MINUTE = 100.0  # $100/min baseline
_DEFAULT_ENGINEER_HOURLY_RATE = 150.0  # $150/hour
_DEFAULT_ENGINEERS_PER_INCIDENT = 3
_DEFAULT_CHURN_RATE_PER_HOUR = 0.001  # 0.1% per hour of downtime
_DEFAULT_CUSTOMER_LTV = 5000.0  # $5000 lifetime value
_DEFAULT_CUSTOMER_COUNT = 1000
_DEFAULT_SLA_CREDIT_PERCENT = 10.0


class IncidentCostCalculator:
    """Calculate financial impact of infrastructure incidents."""

    def __init__(
        self,
        default_revenue_per_minute: float = _DEFAULT_REVENUE_PER_MINUTE,
        default_customer_count: int = _DEFAULT_CUSTOMER_COUNT,
        default_customer_ltv: float = _DEFAULT_CUSTOMER_LTV,
    ):
        self._rev_per_min = default_revenue_per_minute
        self._customer_count = default_customer_count
        self._customer_ltv = default_customer_ltv

    def calculate_component_cost(
        self,
        graph: InfraGraph,
        component_id: str,
        downtime_minutes: int = 60,
    ) -> ComponentCost | None:
        """Calculate cost of a single component failure."""
        comp = graph.get_component(component_id)
        if comp is None:
            return None

        breakdowns: list[CostBreakdown] = []

        # Revenue loss
        rev_per_min = comp.cost_profile.revenue_per_minute or self._rev_per_min
        revenue_loss = rev_per_min * downtime_minutes
        breakdowns.append(CostBreakdown(
            category=CostCategory.REVENUE_LOSS,
            amount_usd=round(revenue_loss, 2),
            description=f"Revenue loss during {downtime_minutes}min outage",
            calculation=f"${rev_per_min:.2f}/min × {downtime_minutes}min",
        ))

        # SLA credits
        sla_pct = comp.cost_profile.sla_credit_percent or _DEFAULT_SLA_CREDIT_PERCENT
        monthly_value = comp.cost_profile.monthly_contract_value or (
            rev_per_min * 60 * 24 * 30
        )
        sla_credits = monthly_value * (sla_pct / 100)
        if downtime_minutes > 43:  # More than ~99.9% monthly budget
            breakdowns.append(CostBreakdown(
                category=CostCategory.SLA_CREDITS,
                amount_usd=round(sla_credits, 2),
                description="SLA credit obligation triggered",
                calculation=f"${monthly_value:.0f} × {sla_pct}%",
            ))

        # Engineer time
        eng_rate = comp.cost_profile.recovery_engineer_cost or _DEFAULT_ENGINEER_HOURLY_RATE
        team_size = comp.cost_profile.recovery_team_size or _DEFAULT_ENGINEERS_PER_INCIDENT
        eng_hours = downtime_minutes / 60 * 1.5  # 1.5x for diagnostics + fix
        eng_cost = eng_rate * eng_hours * team_size
        breakdowns.append(CostBreakdown(
            category=CostCategory.ENGINEER_TIME,
            amount_usd=round(eng_cost, 2),
            description=f"{team_size} engineers × {eng_hours:.1f} hours",
            calculation=f"${eng_rate:.0f}/hr × {eng_hours:.1f}hr × {team_size}",
        ))

        # Customer churn
        churn_rate = comp.cost_profile.churn_rate_per_hour_outage or _DEFAULT_CHURN_RATE_PER_HOUR
        ltv = comp.cost_profile.customer_ltv or self._customer_ltv
        churn_hours = downtime_minutes / 60
        churned = int(self._customer_count * churn_rate * churn_hours)
        churn_cost = churned * ltv
        if churn_cost > 0:
            breakdowns.append(CostBreakdown(
                category=CostCategory.CUSTOMER_CHURN,
                amount_usd=round(churn_cost, 2),
                description=f"Estimated {churned} customers churned",
                calculation=f"{self._customer_count} × {churn_rate}/hr × {churn_hours:.1f}hr × ${ltv:.0f}",
            ))

        # Data loss (for databases/storage without backups)
        if (
            comp.type in (ComponentType.DATABASE, ComponentType.STORAGE)
            and not comp.security.backup_enabled
        ):
            data_loss_cost = comp.cost_profile.data_loss_cost_per_gb or 1000.0
            estimated_gb = 10  # Assume 10GB at risk
            breakdowns.append(CostBreakdown(
                category=CostCategory.DATA_LOSS,
                amount_usd=round(data_loss_cost * estimated_gb, 2),
                description="Potential data loss (no backups)",
                calculation=f"${data_loss_cost:.0f}/GB × {estimated_gb}GB",
            ))

        # Regulatory fine (for compliance-sensitive components)
        if comp.compliance_tags.pci_scope or comp.compliance_tags.contains_pii:
            fine = 50000  # Baseline regulatory fine
            breakdowns.append(CostBreakdown(
                category=CostCategory.REGULATORY_FINE,
                amount_usd=fine,
                description="Potential regulatory fine (PCI/PII data involved)",
                calculation="Baseline regulatory penalty",
            ))

        total = sum(b.amount_usd for b in breakdowns)

        # Risk adjustment: probability based on replicas and failover
        risk_factor = 1.0
        if comp.replicas > 1:
            risk_factor *= 0.1 ** (comp.replicas - 1)  # exponential reduction
        if comp.failover.enabled:
            risk_factor *= 0.1
        risk_adjusted = total * min(risk_factor, 1.0)

        return ComponentCost(
            component_id=component_id,
            component_name=comp.name,
            component_type=comp.type.value,
            downtime_minutes=downtime_minutes,
            breakdowns=breakdowns,
            total_cost_usd=round(total, 2),
            risk_adjusted_cost=round(risk_adjusted, 2),
        )

    def calculate_scenario_cost(
        self,
        graph: InfraGraph,
        component_id: str,
        downtime_minutes: int = 60,
    ) -> ScenarioCost | None:
        """Calculate cost of a failure scenario including cascading impact."""
        comp = graph.get_component(component_id)
        if comp is None:
            return None

        affected = graph.get_all_affected(component_id)
        all_ids = [component_id] + list(affected)
        component_costs: list[ComponentCost] = []

        for cid in all_ids:
            cost = self.calculate_component_cost(graph, cid, downtime_minutes)
            if cost is not None:
                component_costs.append(cost)

        total = sum(c.total_cost_usd for c in component_costs)
        cost_per_min = total / max(downtime_minutes, 1)

        severity = "SEV4"
        if total > 100000:
            severity = "SEV1"
        elif total > 50000:
            severity = "SEV2"
        elif total > 10000:
            severity = "SEV3"

        return ScenarioCost(
            scenario_name=f"{comp.name} failure",
            affected_components=[c.component_name for c in component_costs],
            total_downtime_minutes=downtime_minutes,
            component_costs=component_costs,
            total_cost_usd=round(total, 2),
            cost_per_minute=round(cost_per_min, 2),
            severity=severity,
        )

    def full_analysis(
        self,
        graph: InfraGraph,
        downtime_minutes: int = 60,
    ) -> CostReport:
        """Calculate cost for all components and generate full report."""
        if not graph.components:
            return CostReport(
                component_costs=[],
                total_annual_risk_usd=0,
                highest_risk_component="N/A",
                highest_risk_cost=0,
                cost_by_category={},
                roi_of_improvements=[],
                recommendations=[],
            )

        costs: list[ComponentCost] = []
        for cid in graph.components:
            cost = self.calculate_component_cost(graph, cid, downtime_minutes)
            if cost is not None:
                costs.append(cost)

        # Annual risk estimate (assume 12 incidents/year baseline)
        annual_risk = sum(c.risk_adjusted_cost for c in costs) * 12

        # Highest risk component
        highest = max(costs, key=lambda c: c.risk_adjusted_cost) if costs else None

        # Cost by category
        cat_totals: dict[str, float] = {}
        for cost in costs:
            for bd in cost.breakdowns:
                cat_totals[bd.category.value] = (
                    cat_totals.get(bd.category.value, 0) + bd.amount_usd
                )

        # ROI of improvements
        roi = self._calculate_roi(graph, costs)

        # Recommendations
        recs = self._generate_recommendations(costs, annual_risk)

        return CostReport(
            component_costs=costs,
            total_annual_risk_usd=round(annual_risk, 2),
            highest_risk_component=highest.component_name if highest else "N/A",
            highest_risk_cost=highest.risk_adjusted_cost if highest else 0,
            cost_by_category=cat_totals,
            roi_of_improvements=roi,
            recommendations=recs,
        )

    def _calculate_roi(
        self, graph: InfraGraph, costs: list[ComponentCost]
    ) -> list[dict]:
        """Calculate ROI of resilience improvements."""
        roi_items: list[dict] = []

        for cost in costs:
            comp = graph.get_component(cost.component_id)
            if comp is None:
                continue

            # ROI of adding a replica
            if comp.replicas <= 1 and cost.risk_adjusted_cost > 100:
                monthly_infra = comp.cost_profile.hourly_infra_cost * 720  # 30 days
                annual_savings = cost.risk_adjusted_cost * 12 * 0.9  # 90% risk reduction
                roi_months = (monthly_infra / max(annual_savings / 12, 1))
                roi_items.append({
                    "component": comp.name,
                    "improvement": "Add replica",
                    "monthly_cost": round(monthly_infra, 2),
                    "annual_risk_reduction": round(annual_savings, 2),
                    "roi_months": round(roi_months, 1),
                    "priority": "high" if annual_savings > 10000 else "medium",
                })

            # ROI of enabling failover
            if not comp.failover.enabled and cost.risk_adjusted_cost > 50:
                failover_cost = 50  # Assumed monthly cost
                annual_savings = cost.risk_adjusted_cost * 12 * 0.5
                roi_items.append({
                    "component": comp.name,
                    "improvement": "Enable failover",
                    "monthly_cost": failover_cost,
                    "annual_risk_reduction": round(annual_savings, 2),
                    "roi_months": round(failover_cost / max(annual_savings / 12, 1), 1),
                    "priority": "high" if annual_savings > 5000 else "medium",
                })

        roi_items.sort(key=lambda x: x.get("annual_risk_reduction", 0), reverse=True)
        return roi_items[:10]

    def _generate_recommendations(
        self, costs: list[ComponentCost], annual_risk: float
    ) -> list[str]:
        """Generate cost-based recommendations."""
        recs: list[str] = []

        if annual_risk > 100000:
            recs.append(
                f"Annual risk exposure is ${annual_risk:,.0f} — "
                f"immediate resilience improvements needed"
            )
        elif annual_risk > 10000:
            recs.append(
                f"Annual risk exposure is ${annual_risk:,.0f} — "
                f"review highest-risk components"
            )

        # Find components with data loss risk
        data_loss = [
            c for c in costs
            if any(b.category == CostCategory.DATA_LOSS for b in c.breakdowns)
        ]
        if data_loss:
            names = ", ".join(c.component_name for c in data_loss[:3])
            recs.append(f"Enable backups for: {names} (data loss risk)")

        # Find single-instance components with high cost
        spof_cost = [
            c for c in costs
            if c.risk_adjusted_cost > 1000
        ]
        if spof_cost:
            names = ", ".join(c.component_name for c in spof_cost[:3])
            recs.append(f"Highest financial risk components: {names}")

        return recs
